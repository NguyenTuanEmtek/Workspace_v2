import grpc
from kuksa_client.grpc import VSSClient

try:
    with VSSClient(host="localhost", port = 60000) as client:
        print("Connected!")
        print(client.get_current_values(['Vehicle.Speed']))
except Exception as e:
    print(f"Error: {e}")