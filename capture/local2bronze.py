import psutil, random, json, os, boto3
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

def configure_env():
    BASE_DIR = Path(__file__).parent.parent
    ENV_PATH = BASE_DIR / ".env"

    load_dotenv(ENV_PATH)


def get_system_data():
    network = psutil.net_io_counters()
    now = datetime.now()
    formatt_date = now.strftime("%Y-%m-%d %H:%M:%S")

    return {
        "date_time": formatt_date,
        "CPU_Usage": psutil.cpu_percent(interval=1),
        "RAM_Usage": psutil.virtual_memory().percent,
        "Bytes_Sent": network.bytes_sent,
        "Bytes_Recv": network.bytes_recv,
        "Active_sessions": psutil.net_connections(kind='inet')
    }


def get_antena_data():
    system = get_system_data()

    return {
        "date_time": system["date_time"],
        "ID_antena": 1,
        "Bytes_Sent": system["Bytes_Sent"],
        "Bytes_Recv": system["Bytes_Recv"],
        "Active_conn": random.randint(5, 50),
        "CPU_Usage": system["CPU_Usage"],
        "RAM_Usage": system["RAM_Usage"]
    }


def get_firewall_data():
    system = get_system_data()
    network = psutil.net_io_counters()
    dropped = (network.dropin + network.dropout)
    ip = None
    if dropped > 100:
        ip = "192.168.1.100"
    return {
        "date_time": system["date_time"],
        "Active_sessions": len(system["Active_sessions"]),
        "Dropped_packets": network.dropin + network.dropout,
        "top_blocked_ip": ip,
        "CPU_Usage": system["CPU_Usage"],
        "RAM_Usage": system["RAM_Usage"],
        "Bytes_Sent": system["Bytes_Sent"],
        "Bytes_Recv": system["Bytes_Recv"]
    }

def create_json():
    now = datetime.now()
    formatt_date = now.strftime("%Y-%m-%d_%H-%M")

    data = {
        "antena": get_antena_data(),
        "firewall": get_firewall_data()
    }

    file_name = f"{data['antena']['ID_antena']}_{formatt_date}.json"

    with open(f"data/{file_name}", "w") as file:
        json.dump(data, file, indent=4)

    return file_name
    
def create_s3_conn():
    s3 = boto3.client(
        "s3",
        region_name=os.getenv("BUCKET_REGION")
    )
    return s3

def upload_json_file(file, s3):
    s3.upload_file(
        f"data/{file}",
        os.getenv("BUCKET_NAME"),
        f"raw/{file}"
    )

def remove_json(file):
    try:
        os.remove(f"data/{file}")
        print(f"O arquivo '{file}' foi apagado com sucesso.")
    except FileNotFoundError:
        print(f"O arquivo '{file}' não foi encontrado.")
    except PermissionError:
        print("Você não tem permissão para apagar este arquivo.")

def main():
    file_name = create_json()
    configure_env()
    s3 = create_s3_conn()
    upload_json_file(file_name, s3)
    remove_json(file_name)


main()