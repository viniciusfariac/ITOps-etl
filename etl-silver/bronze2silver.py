import json, os, boto3
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path
import pandas as pd


def configure_env():
    BASE_DIR = Path(__file__).parent.parent
    ENV_PATH = BASE_DIR / ".env"

    load_dotenv(ENV_PATH)

def create_s3_conn():
    s3 = boto3.client(
        "s3",
        region_name=os.getenv("BUCKET_REGION")
    )
    return s3


def get_files(s3):
    response = s3.list_objects_v2(
    Bucket=os.getenv("BUCKET_NAME"),
    Prefix="raw/"
    )
    return response.get("Contents", [])


def clean_df(data):
    data["CPU_Usage"] = round(float(data["CPU_Usage"]), 2)
    data["RAM_Usage"] = round(float(data["RAM_Usage"]), 2)
        
    data["Bytes_Sent"] = int(data["Bytes_Sent"])
    data["Bytes_Recv"] = int(data["Bytes_Recv"])

    data = load_status(data)

    return data   


def load_status(data):
    if data["CPU_Usage"] > 80:
        data["status_cpu"] = "gargalo de processamento"
    else:
        data["status_cpu"] = "normal"

    if data["RAM_Usage"] > 75:
        data["status_ram"] = "OOM (Out Of Memory)"
    else:
        data["status_ram"] = "normal"

    if "Active_conn" in data:
        if data["Active_conn"] > 40:
            data["status_active_conn"] = "alta densidade"
        else:
            data["status_active_conn"] = "normal"

    return data

def json_to_df(s3, files):
    for file in files:
        key = file["Key"]
        
 
        if not key.endswith(".json"):
            continue

        index_id = key.find("_")
        index_json = key.find(".json")
        file_name = key[index_id + 1:index_json]

        
        date_file = datetime.strptime(file_name, "%Y-%m-%d_%H-%M")
        date_now = datetime.now()
        
        seconds = (date_now - date_file).total_seconds()
        
        if (seconds > 180 or seconds < 0):
            continue
        
        response = s3.get_object(
            Bucket=os.getenv("BUCKET_NAME"),
            Key=key
        )

        data = json.loads(response["Body"].read())

        antena = clean_df(data["antena"])
        firewall = clean_df(data["firewall"])

        convert_csv(antena, "antena", key)
        convert_csv(firewall, "firewall", key)

    df_antena = pd.read_csv("csv/antena.csv")
    df_firewall = pd.read_csv("csv/firewall.csv")

    df_antena = calculate_mbps_antenas(df_antena)
    df_firewall = calculate_mbps_firewall(df_firewall)
    df_firewall = check_consistency(df_antena, df_firewall)

    df_antena.to_csv("csv/antena.csv",index=False)

    df_firewall.to_csv("csv/firewall.csv",index=False)

def convert_csv(data, type, key):
    data["source_file"] = key
    new_df = pd.DataFrame([data])

    os.makedirs("csv", exist_ok=True)
    path = f"csv/{type}.csv"

    if os.path.exists(path):
        df = pd.read_csv(path)
        if key in df["source_file"].values:
            return
        
        df = pd.concat([df, new_df], ignore_index=True)
    else:
        df = new_df

    df.to_csv(path, index=False)

def calculate_mbps_antenas(df):
    df["date_time"] = pd.to_datetime(df["date_time"])

    df = df.sort_values(["ID_antena", "date_time"])

    diff_bytes = df.groupby("ID_antena")["Bytes_Sent"].diff()

    interval = (
        df.groupby("ID_antena")["date_time"]
          .diff()
          .dt.total_seconds()
    )

    df["Mbps"] = (diff_bytes * 8 / interval / 1_000_000)

    return df

def calculate_mbps_firewall(df):

    df["date_time"] = pd.to_datetime(df["date_time"])

    df = df.sort_values("date_time")

    diff_bytes = df["Bytes_Sent"].diff()

    interval = df["date_time"].diff().dt.total_seconds()

    df["Mbps"] = ( diff_bytes * 8 / interval / 1_000_000 )

    return df

def check_consistency(df_antena, df_firewall):
    df_antena["date_time"] = pd.to_datetime(df_antena["date_time"])
    df_firewall["date_time"] = pd.to_datetime(df_firewall["date_time"])

    df_antena["date_time_min"] = df_antena["date_time"].dt.floor("min")
    df_firewall["date_time_min"] = df_firewall["date_time"].dt.floor("min")

    antenas = (
        df_antena
        .groupby("date_time_min")["Mbps"]
        .sum()
        .reset_index()
    )

    df_firewall = pd.merge(
    df_firewall,
    antenas,
    on="date_time_min",
    how="inner",
    suffixes=("_firewall", "_antenas"))   

    df_firewall["diferenca_percentual"] = (abs(
        df_firewall["Mbps_antenas"] - df_firewall["Mbps_firewall"] ) / df_firewall["Mbps_firewall"] * 100)
    
    df_firewall["consistencia"] = (df_firewall["diferenca_percentual"] <= 3)

    return df_firewall

def remove_file(file):
    try:
        os.remove(f"csv/{file}.csv")
    except FileNotFoundError:
        print(f"O arquivo {file} não foi encontrado.")
    except PermissionError:
        print("Você não tem permissão para apagar este arquivo.")

def upload_csv(file, s3):
    now = datetime.now()
    formatt_date = now.strftime("%Y-%m-%d_%H-%M")
    s3.upload_file(
        f"csv/{file}.csv",
        os.getenv("BUCKET_NAME"),
        f"trusted/{file}_{formatt_date}.csv"
    )

def main():
    configure_env()
    s3 = create_s3_conn()
    files = get_files(s3)
    json_to_df(s3, files)
    upload_csv("antena", s3)
    upload_csv("firewall", s3)
    remove_file("antena")
    remove_file("firewall")
    print("Envio bem sucedido", datetime.now())


main()