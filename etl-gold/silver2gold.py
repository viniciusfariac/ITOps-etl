import os
import io
import boto3
import pandas as pd

from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

BASE_DIR = Path(__file__).parent
CSV_DIR = BASE_DIR / "csv"

def configure_env():

    BASE_DIR = Path(__file__).parent.parent
    ENV_PATH = BASE_DIR / ".env"

    load_dotenv(ENV_PATH)


def create_s3_conn():

    return boto3.client(
        "s3",
        region_name=os.getenv("BUCKET_REGION")
    )

def get_silver_csv(s3, prefix, limit):

    response = s3.list_objects_v2(
        Bucket=os.getenv("BUCKET_NAME"),
        Prefix=prefix
    )

    files = []
    for file in response.get("Contents", []):
        if file["Key"].endswith(".csv"):
            files.append(file)

    if not files:
        raise Exception(f"Nenhum arquivo encontrado em {prefix}")


    files.sort(key=lambda file: file["LastModified"], reverse=True)
        
    return files[:limit]


def merging_csv(files, s3):
    dfs = []

    for file in files:
        df = read_silver(s3, file["Key"])
        dfs.append(df)

    return pd.concat(dfs, ignore_index=True)


def read_silver(s3, key):
    response = s3.get_object(
        Bucket=os.getenv("BUCKET_NAME"),
        Key=key
    )

    df = pd.read_csv(response["Body"])

    return df

def remove_duplicates(df_antena, df_firewall):

    df_antena = df_antena.drop_duplicates(
        subset=["ID_antena", "date_time"]
    )

    df_firewall = df_firewall.drop_duplicates(
        subset=["date_time"]
    )

    return df_antena, df_firewall

def dead_zone_report(df_antena: pd.DataFrame):
    df_dead_zone = (
        df_antena.groupby('ID_antena')
        .agg(
            mbps_average=("Mbps", "mean"),
            conn_average=("Active_conn", "mean"),
            cpu_average=("CPU_Usage", "mean"),
            ram_average=("RAM_Usage", "mean")
        )
        .reset_index()
    )
    df_dead_zone["classificacao"] = "normal"
    
    condicao = (
        (df_dead_zone["mbps_average"] <  0.5) &
        (df_dead_zone["conn_average"] < 7) &
        (df_dead_zone["cpu_average"] < 20) &
        (df_dead_zone["ram_average"]  < 20)
    )

    df_dead_zone.loc[condicao, "classificacao"] = "subutilizada"

    return df_dead_zone
    
def hardware_efficienct_report(df_antena: pd.DataFrame):

    df = (
        df_antena.groupby("ID_antena")
        .agg(
            mbps_average=("Mbps", "mean"),
            cpu_average=("CPU_Usage", "mean")
        )
        .reset_index()
    )

    df["cpu_network_relationship"] = df["mbps_average"] / df["cpu_average"]

    median = df["cpu_network_relationship"].median()

    df["efficiency"] = "Baixa"

    df.loc[df["cpu_network_relationship"] >= median, "efficiency"] = "Alta"
    return df

def convert_csv(df: pd.DataFrame, filename):
    CSV_DIR.mkdir(exist_ok=True)
    df.to_csv(CSV_DIR / f"{filename}.csv", index=False)


def main():
    configure_env()
    s3 = create_s3_conn()
    files_antena = get_silver_csv(s3, "trusted/antena_", 10)
    df_antena = merging_csv(files_antena, s3)
    files_firewall = get_silver_csv(s3, "trusted/firewall_", 10)
    df_firewall  = merging_csv(files_firewall, s3)

    df_antena, df_firewall = remove_duplicates(df_antena, df_firewall)
    df_dead_zone = dead_zone_report(df_antena)
    df_hardware_efficiency = hardware_efficienct_report(df_antena)

    dead_zone_file = "zonas_subutilizadas"
    hardware_efficienct_file = "eficiencia_hardware"

    convert_csv(df_dead_zone, dead_zone_file)
    convert_csv(df_hardware_efficiency, hardware_efficienct_file)

    upload_csv(dead_zone_file, s3)
    upload_csv(hardware_efficienct_file, s3)

    remove_file(dead_zone_file)
    remove_file(hardware_efficienct_file)
    print("Envio bem sucedido", datetime.now())


def upload_csv(file, s3):
    now = datetime.now()
    formatt_date = now.strftime("%Y-%m-%d_%H-%M")

    s3.upload_file(
        str(CSV_DIR / f"{file}.csv"),
        os.getenv("BUCKET_NAME"),
        f"client/{file}/{file}_{formatt_date}.csv"
    )

def remove_file(file):
    try:
        os.remove(CSV_DIR / f"{file}.csv")
    except FileNotFoundError:
        print(f"O arquivo {file} não foi encontrado.")
    except PermissionError:
        print("Você não tem permissão para apagar este arquivo.")


main()


