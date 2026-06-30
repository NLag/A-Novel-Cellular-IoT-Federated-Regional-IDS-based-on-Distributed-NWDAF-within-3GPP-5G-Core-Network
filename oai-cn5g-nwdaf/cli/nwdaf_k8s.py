import json
import requests
import typer
import os

# Get Minikube IP and NodePort from environment or use defaults
MINIKUBE_IP = os.getenv('MINIKUBE_IP', '192.168.85.2')
NODEPORT = os.getenv('NWDAF_NODEPORT', '31170')

analytics_url = f'http://{MINIKUBE_IP}:{NODEPORT}/nnwdaf-analyticsinfo/v1/analytics'
subscription_url = f'http://{MINIKUBE_IP}:{NODEPORT}/nnwdaf-eventssubscription/v1/subscriptions'

app = typer.Typer()

@app.command()
def analytics(
    json_file: str = typer.Argument(..., help="JSON analytics request file name"),
):
    """Perform analytics based on the provided JSON request file."""
    with open(json_file) as file:
        data = json.load(file)
    
    event_id = data['event-id']
    ana_req = json.dumps(data['ana-req'])
    event_filter = json.dumps(data['event-filter'])
    supported_features = json.dumps(data['supported-features'])
    tgt_ue = json.dumps(data['tgt-ue'])
    
    params = {
        'event-id': event_id,
        'ana-req': ana_req,
        'event-filter': event_filter,
        'supported-features': supported_features,
        'tgt-ue': tgt_ue
    }
    
    typer.echo(f"Calling: {analytics_url}")
    response = requests.get(analytics_url, params=params)
    typer.echo(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        try:
            parsed_response = response.json()
            typer.echo(json.dumps(parsed_response, indent=4))
        except:
            typer.echo(response.text)
    else:
        typer.echo(f"Error: {response.text}")

@app.command()
def subscribe(
    subscription_file: str = typer.Argument(..., help="JSON subscription file name"),
):
    """Subscribe to events based on the provided JSON subscription file."""
    with open(subscription_file) as f:
        subscription_data = json.load(f)
    
    typer.echo(f"Calling: {subscription_url}")
    response = requests.post(subscription_url, json=subscription_data)
    typer.echo(f"Status: {response.status_code}")
    typer.echo(response.text)

if __name__ == '__main__':
    app()
