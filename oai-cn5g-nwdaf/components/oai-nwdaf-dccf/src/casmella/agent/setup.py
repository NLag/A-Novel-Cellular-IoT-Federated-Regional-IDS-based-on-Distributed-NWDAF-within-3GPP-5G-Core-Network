"""Setup."""
from setuptools import setup, find_packages

setup(
    name='fiveg-trafficmeter-controller',
    version='0.1',
    description='Telco EBPF Controller Module for Observability',
    author='Abderaouf KHICHANE',
    author_email='abderaouf.khichane@orange.com',
    packages=find_packages('src/agent, exclude=["tests"]'),
    scripts=['main.py'],
    install_requires=['kubernetes','prometheus_client','uvicorn','fastapi']
)