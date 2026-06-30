"""
A Python client for Prometheus APIs.
"""
import time
import json
import requests
import pandas as pd
import numpy as np

class PrometheusInstance():
    """
    A PrometheusInstance class.

    Attributes
    ----------
    url: Prometheus server url (e.g. http://localhost:9090).
    """

    # Init
    def __init__(self, prometheus_address):
        """
        Create a PrometheusInstance object for a Prometheus server instance.

        Parameters
        ----------
        prometheus_address=<str>: Prometheus server address (e.g. localhost:9090).
        """
        self.url = f'http://{prometheus_address}'

    # Health check
    def health_check(self):
        """
        Health check
        ----------
        Check Prometheus health.

        Parameters
        ----------

        Returns
        ----------
        Boolean.
        """
        request_api_path = f'{self.url}/-/healthy'
        response = requests.get(request_api_path)
        return response.status_code == 200

    # Readiness check
    def readiness_check(self):
        """
        Readiness check
        ----------
        Check Prometheus readiness.

        Parameters
        ----------

        Returns
        ----------
        Boolean.
        """
        request_api_path = f'{self.url}/-/ready'
        response = requests.get(request_api_path)
        return response.status_code == 200

    # Perform query
    @staticmethod
    def _perform_http_get_request(request_api_path: str, request_params: dict):
        response = requests.get(request_api_path, params=request_params)
        return response.json()

    # Parse result
    @staticmethod
    def _parse_json_result(response_json: dict):
        if 'data' not in response_json:
            return None
        response_data = response_json['data']
        result_type = response_data.get('resultType', None)
        if result_type == 'vector':
            result = response_data['result']
            return pd.Series(
                (np.float64(res['value'][1]) for res in result),
                index=(json.dumps(res['metric']) for res in result)
            )
        if result_type == 'matrix':
            result = response_data['result']
            pandas_dataframe = pd.DataFrame({
                json.dumps(res['metric']): pd.Series(
                    (np.float64(val[1]) for val in res['values']),
                    index=(val[0] for val in res['values'])
                ) for res in result
            })
            return pandas_dataframe
        # ## Returns without formatting
        return response_data

    # Instant queries
    def instant_query(self, query, timestamp=None, timeout=None):
        """
        Instant queries
        ----------
        Evaluate an instant query at a single point in time.

        Parameters
        ----------
        query=<str>: Prometheus expression query string.
        timestamp=<str|int|float>: Evaluation timestamp (rfc3339 | unix_timestamp). Optional. Defaults to the current Prometheus server time.
        timeout=<str>: Evaluation timeout (e.g. '1m'). Optional. Defaults to and is capped by the value of the -query.timeout flag.

        Returns
        ----------
        Pandas Series.
        """
        request_api_path = f'{self.url}/api/v1/query'
        query = query.encode('utf-8')
        request_params = {
            'query': query
        }
        if timestamp is not None:
            request_params['time'] = timestamp
        if timeout is not None:
            request_params['timeout'] = timeout
        response_json = self._perform_http_get_request(request_api_path, request_params)
        if response_json['status'] == 'error':
            return None, response_json['error']
        # ## Status is 'success'
        pandas_dataframe = self._parse_json_result(response_json)
        return pandas_dataframe, None

    # Range queries
    def range_query(self, query, start_timestamp=time.time()-30*60, end_timestamp=time.time(), step='10s', timeout=None):
        """
        Range queries
        ----------
        Evaluate an instant query at a single point in time.

        Parameters
        ----------
        query=<str>: Prometheus expression query string.
        start_timestamp=<str>: Start timestamp (rfc3339 | unix_timestamp). Optional. Defaults to the current timestamp minus 30 minutes.
        end_timestamp=<str>: End timestamp (rfc3339 | unix_timestamp). Optional. Defaults to the current timestamp.
        step=<str|int|float>: Query resolution step  (e.g. 30, '30s', '1m'). Optional. Defaults to '10s'.
        timeout=<str>: Evaluation timeout. Optional. Defaults to and is capped by the value of the -query.timeout flag.

        Returns
        ----------
        Pandas DataFrame.
        """
        request_api_path = f'{self.url}/api/v1/query_range'
        query = query.encode('utf-8')
        request_params = {
            'query': query,
            'start': start_timestamp,
            'end': end_timestamp,
            'step': str(step),
        }
        if timeout is not None:
            request_params['timeout'] = timeout
        response_json = self._perform_http_get_request(request_api_path, request_params)
        if response_json['status'] == 'error':
            return None, response_json['error']
        # ## Status is 'success'
        pandas_dataframe = self._parse_json_result(response_json)
        return pandas_dataframe, None

    # Formatting query expressions
    def formatting_query(self, query):
        """
        Formatting query expressions
        ----------
        Format a PromQL expression in a prettified way.

        Parameters
        ----------
        query=<str>: Prometheus expression query string.

        Returns
        ----------
        Query string (str).
        """
        request_api_path = f'{self.url}/api/v1/format_query'
        query = query.encode('utf-8')
        request_params = {
            'query': query
        }
        response_json = self._perform_http_get_request(request_api_path, request_params)
        if response_json['status'] == 'error':
            return None, response_json['error']
        # ## Status is 'success'
        response_data = self._parse_json_result(response_json)
        return response_data

    # Finding series by label matchers
    def find_series(self, match=None, start_timestamp=None, end_timestamp=None):
        """
        Finding series by label matchers
        ----------
        Return the list of time series that match a certain label set.

        Parameters
        ----------
        start_timestamp=<str>: Start timestamp (rfc3339 | unix_timestamp). Optional.
        end_timestamp=<str>: End timestamp (rfc3339 | unix_timestamp). Optional.

        Returns
        ----------
        List of time series (list).
        """
        print(f"match {match} parameter will not be used")
        request_api_path = f'{self.url}/api/v1/series'
        request_params = {
            'start': start_timestamp,
            'end': end_timestamp
        }
        response_json = self._perform_http_get_request(request_api_path, request_params)
        if response_json['status'] == 'error':
            return None, response_json['error']
        # ## Status is 'success'
        response_data = self._parse_json_result(response_json)
        return response_data

    # Getting label names
    def get_label_names(self, match=None, start_timestamp=None, end_timestamp=None):
        """
        Getting label names:
        Return a list of label names.

        Parameters
        ----------
        start_timestamp=<str>: Start timestamp (rfc3339 | unix_timestamp). Optional.
        end_timestamp=<str>: End timestamp (rfc3339 | unix_timestamp). Optional.

        Returns
        ----------
        List of label names (list).
        """
        print(f"match {match} parameter will not be used")
        request_api_path = f'{self.url}/api/v1/labels'
        request_params = {
            'start': start_timestamp,
            'end': end_timestamp
        }
        response_json = self._perform_http_get_request(request_api_path, request_params)
        if response_json['status'] == 'error':
            return None, response_json['error']
        # ## Status is 'success'
        response_data = self._parse_json_result(response_json)
        return response_data

    # Querying label values
    def query_label_values(self, label_name, match=None, start_timestamp=None, end_timestamp=None):
        """
        Querying label values
        ----------
        Return a list of label values for a provided label name.

        Parameters
        ----------
        label_name=<str>: Label name.
        start_timestamp=<str>: Start timestamp (rfc3339 | unix_timestamp). Optional.
        end_timestamp=<str>: End timestamp (rfc3339 | unix_timestamp). Optional.

        Returns
        ----------
        List of label names (list).
        """
        print(f"match {match} parameter will not be used")
        request_api_path = f'{self.url}/api/v1/label/{label_name}/values'
        request_params = {
            'start': start_timestamp,
            'end': end_timestamp
        }
        response_json = self._perform_http_get_request(request_api_path, request_params)
        if response_json['status'] == 'error':
            return None, response_json['error']
        # ## Status is 'success'
        response_data = self._parse_json_result(response_json)
        return response_data

    # Querying exemplars (TODO)

    # Targets
    def get_targets(self, state=None):
        """
        Targets
        ----------
        Return an overview of the current state of the Prometheus target discovery.

        Parameters
        ----------
        state=<str>: State of targets ('active' | 'dropped' | 'any'). Optional.

        Returns
        ----------
        List of targets (list).
        """
        request_api_path = f'{self.url}/api/v1/targets'
        request_params = {
            'state': state
        }
        response_json = self._perform_http_get_request(request_api_path, request_params)
        if response_json['status'] == 'error':
            return None, response_json['error']
        # ## Status is 'success'
        response_data = self._parse_json_result(response_json)
        return response_data

    # Rules
    def get_rules(self, rule_type=None):
        """
        Rules
        ----------
        Return an overview of the current state of the Prometheus target discovery.

        Parameters
        ----------
        rule_type=<str>: Type of rules ('alert' | 'record'). Optional.

        Returns
        ----------
        List of targets (list).
        """
        request_api_path = f'{self.url}/api/v1/rules'
        request_params = {
            'type': rule_type
        }
        response_json = self._perform_http_get_request(request_api_path, request_params)
        if response_json['status'] == 'error':
            return None, response_json['error']
        # ## Status is 'success'
        response_data = self._parse_json_result(response_json)
        return response_data

    # Alerts
    def get_alerts(self):
        """
        Alerts
        ----------
        Return a list of all active alerts.

        Parameters
        ----------

        Returns
        ----------
        List of alerts (list).
        """
        request_api_path = f'{self.url}/api/v1/alerts'
        response_json = self._perform_http_get_request(request_api_path, {})
        if response_json['status'] == 'error':
            return None, response_json['error']
        # ## Status is 'success'
        response_data = self._parse_json_result(response_json)
        return response_data
