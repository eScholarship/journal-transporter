"""Handler for HTTP connections to host servers. Subclass of AbstractConnection."""

import json
import requests

from typing import Union

from journal_transporter.transfer.abstract_connection import AbstractConnection


class HTTPConnection(AbstractConnection):

    def get(self, path: str, is_absolute: bool = False, **params) -> Union[list, dict]:
        """
        Submits a GET request to the connection.

        Parameters:
            path: str
                The path to be appended to the server's "host" value
            is_absolute: bool
                Is the URL absolute? If false, it will be combined with the host to build a full URL.
            params: dict
                Arbitrary parameters to be submitted as URL params

        Returns: Union[list, dict]
            The response JSON.
        """
        url = path if is_absolute else f"{self.host.strip('/')}/{path.strip('/')}"
        request_opts = self.__build_get_params(params)
        response = requests.get(url, **request_opts)
        return response

    def post(self, path: str, data) -> dict:
        """
        Submits a POST request to the connection.

        Parameters:
            path: str
                The path to be appended to the server's "host" value
            data: Any
                Any serializable content to be submitted as POST data.

        Returns: Any
            The response content.
        """
        url = f"{self.host.strip('/')}/{path.strip('/')}/"
        request_opts = self.__build_post_params(data.copy())
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36'
        }

        response = None
        if type(data) is list:
            response = []
            for index, record in enumerate(data):
                response.append(requests.post(url, headers=headers, **request_opts))
        else:
            response = requests.post(url, headers=headers, **request_opts)

        return response

    # Private

    def __build_get_params(self, params: dict = None) -> dict:
        ret = {
            **self.__credentials(),
            "params": params
        }

        return {k: v for (k, v) in ret.items() if v is not None}

    def __build_post_params(self, params: dict = None) -> dict:
        files = params.get("files") if "files" in params else None
        data_key = "data" if files else "json"

        data = {}
        for key, value in params.items():
            if not key == "files":
                data[key] = value

        ret = {
            **self.__credentials(),
            "files": files,
            data_key: {"json": json.dumps(data)} if files else data
        }

        return {k: v for (k, v) in ret.items() if v is not None}

    def __credentials(self) -> dict:
        """
        Builds credentials kwargs, if username is defined.

        Returns: dict
            The auth dict to possibly be included in the request.
        """
        if self.username is None: return {}
        return {"auth": (self.username, self.password)}
