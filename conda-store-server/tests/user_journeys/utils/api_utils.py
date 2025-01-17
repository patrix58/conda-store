"""Helper functions for user journeys."""
import time
import uuid
from enum import Enum
from typing import Union

import requests
import utils.time_utils as time_utils

TIMEOUT = 10


class BuildStatus(Enum):
    """Enum for API build status."""

    QUEUED = "QUEUED"
    BUILDING = "BUILDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class NamespaceStatus(Enum):
    OK = "ok"
    ERROR = "error"


class API:
    """
    Helper class for making requests to the API.
    These methods are used to build tests for user journeys
    """

    def __init__(
        self,
        base_url: str,
        token: str = "",
        username: str = "username",
        password: str = "password",
    ) -> None:
        self.base_url = base_url
        self.token = token
        if not token:
            # Log in if no token is provided to set the token
            self._login(username, password)

    def _make_request(
        self,
        endpoint: str,
        method: str = "GET",
        json_data: dict = None,
        headers: dict = None,
        timeout: int = TIMEOUT,
    ) -> requests.Response:
        """Make a request to the API."""
        url = f"{self.base_url}/{endpoint}"
        headers = headers or {}
        headers["Authorization"] = f"Bearer {self.token}"
        response = requests.request(
            method, url, json=json_data, headers=headers, timeout=timeout
        )
        response.raise_for_status()
        return response

    def _login(self, username: str, password: str) -> None:
        """Log in to the API and set an access token."""
        json_data = {"username": username, "password": password}
        response = requests.post(
            f"{self.base_url}/login", json=json_data, timeout=TIMEOUT
        )
        cookies = response.cookies.get_dict()
        token_response = requests.post(
            f"{self.base_url}/api/v1/token", cookies=cookies, timeout=TIMEOUT
        )
        data = token_response.json()
        self.token = data["data"]["token"]

    def create_namespace(
        self,
        namespace: Union[str, None] = None,
        max_iterations: int = 100,
        sleep_time: int = 5,
    ) -> requests.Response:
        """Create a namespace.

        Parameters
        ----------
        namespace : str
            Name of the namespace to create. If None, use a random namespace name
        max_iterations : int
            Max number of times to check whether the namespace was created before failing
        sleep_time : int
            Seconds to wait between each status check

        Returns
        -------
        requests.Response
            Response from the conda-store server
        """
        if namespace is None:
            namespace = self.gen_random_namespace()

        self._make_request(f"api/v1/namespace/{namespace}", method="POST")
        for i in range(max_iterations):
            response = self._make_request(f"api/v1/namespace/{namespace}")
            status = NamespaceStatus(response.json()["status"])
            if status in [NamespaceStatus.OK, NamespaceStatus.ERROR]:
                return response

            time.sleep(sleep_time)

        raise TimeoutError(
            f"Timed out waiting to create namespace {namespace}. Current response: "
            f"{response.json()}"
        )

    def create_token(
        self, namespace: str, role: str, default_namespace: str = "default"
    ) -> requests.Response:
        """Create a token with a specified role in a specified namespace."""
        json_data = {
            "primary_namespace": default_namespace,
            "expiration": time_utils.get_iso8601_time(1),
            "role_bindings": {f"{namespace}/*": [role]},
        }
        return self._make_request("api/v1/token", method="POST", json_data=json_data)

    def create_environment(
        self,
        namespace: str,
        specification_path: str,
        max_iterations: int = 100,
        sleep_time: int = 5,
    ) -> requests.Response:
        """Create an environment.

        Parameters
        ----------
        namespace : str
            Namespace the environment should be written to
        specification_path : str
            Path to conda environment specification file
        max_iterations : int
            Max number of times to check whether the build completed before failing
        sleep_time : int
            Seconds to wait between each status check

        Returns
        -------
        requests.Response
            Response from the conda-store server
        """
        with open(specification_path, "r", encoding="utf-8") as file:
            specification_content = file.read()

        response = self._make_request(
            "api/v1/specification",
            method="POST",
            json_data={"namespace": namespace, "specification": specification_content},
        )
        build_id = response.json()["data"]["build_id"]
        for i in range(max_iterations):
            response = self._make_request(f"api/v1/build/{build_id}/")
            status = BuildStatus(response.json()["data"]["status"])

            if status in [
                BuildStatus.COMPLETED,
                BuildStatus.FAILED,
                BuildStatus.CANCELED,
            ]:
                return response

            time.sleep(sleep_time)

        raise TimeoutError(
            f"Timed out waiting to create namespace {namespace}. Current response: "
            f"{response.json()}"
        )

    def delete_environment(
        self, namespace: str, environment_name: str
    ) -> requests.Response:
        """Delete an environment."""
        return self._make_request(
            f"api/v1/environment/{namespace}/{environment_name}", method="DELETE"
        )

    def delete_namespace(self, namespace: str) -> requests.Response:
        """Delete a namespace."""
        return self._make_request(f"api/v1/namespace/{namespace}", method="DELETE")

    @staticmethod
    def gen_random_namespace() -> str:
        """Generate a random namespace."""
        return uuid.uuid4().hex
