import os
import requests
from requests.auth import HTTPBasicAuth
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Dict, Optional

class JenkinsArtifactFetcher:
    
    def __init__(self, base_url: str, username: str, token: str):
        if not all([base_url, username, token]):
            raise ValueError("Jenkins URL, username, and token must all be provided.")
        
        self.base_url = base_url.rstrip('/')
        self.auth = HTTPBasicAuth(username, token)
        self.timeout = 10  # Seconds

    def _make_request(self, url: str, params: Optional[Dict[str, str]] = None) -> bytes:
        response = requests.get(url, auth=self.auth, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.content

    def get_upstream_build_data(self, job_name: str) -> Dict[str, str]:
        """Fetches ID and timestamp of the latest successful upstream build."""
        url = f"{self.base_url}/job/{job_name}/lastSuccessfulBuild/api/xml"
        content = self._make_request(url)
        
        root = ET.fromstring(content)
        
        result = {}
        for item in ["id", "timestamp"]:
            element = root.find(item)
            if element is None or not element.text:
                raise KeyError(f"Required element '{item}' missing from upstream API response.")
            result[item] = element.text
            
        return result

    def get_downstream_build_params(self, downstream_job: str, upstream_job: str, 
                                    upstream_id: str, platform: str, deploy_type: str) -> Dict[str, str]:
        """Filters downstream builds matching the upstream criteria and returns branch/commit info."""
        url = f"{self.base_url}/job/{downstream_job}/api/xml"
        
        params = {
            "tree": "builds[number,url,actions[parameters[name,value],causes[upstreamProject,upstreamBuild]]]",
            "xpath": f'//build[action/cause/upstreamProject="{upstream_job}" and action/cause/upstreamBuild="{upstream_id}" and action/parameter/value="{platform}" and action/parameter/value="{deploy_type}"]',
            "wrapper": "matches"
        }
        
        content = self._make_request(url, params=params)
        root = ET.fromstring(content)
        
        result = {"BRANCH": "", "COMMIT": ""}
        for parameter in root.iter("parameter"):
            name_el = parameter.find("name")
            value_el = parameter.find("value")
            
            if name_el is not None and value_el is not None and name_el.text in result:
                result[name_el.text] = value_el.text or ""
                
            if all(result.values()):
                break  # Stop early if both are found
                
        if not all(result.values()):
            raise ValueError("Could not extract valid BRANCH and COMMIT from matching downstream job.")
            
        return result


def is_build_recent(timestamp_ms: int, max_hours: int = 24) -> bool:
    # Floor division for standard integer conversion from ms to seconds
    build_seconds = timestamp_ms // 1000 
    
    build_time = datetime.fromtimestamp(build_seconds, tz=timezone.utc)
    now = datetime.now(tz=timezone.utc)
    
    hours_diff = (now - build_time).total_seconds() / 3600
    print(f"Build was started {round(hours_diff, 1)} hours ago.")
    return hours_diff < max_hours


def main():
    JENKINS_URL = os.getenv("JENKINS_URL", "https://your-jenkins-instance.com")
    JENKINS_USER = os.getenv("JENKINS_USER", "your_user")
    JENKINS_SECRET = os.getenv("JENKINS_SECRET", "your_token")
    
    UPSTREAM_JOB = "your_upstream_job"
    DOWNSTREAM_JOB = "your_downstream_job"
    PLATFORM = "your_platform"
    DEPLOY_TYPE = "your_deploy_type"

    try:
        fetcher = JenkinsArtifactFetcher(JENKINS_URL, JENKINS_USER, JENKINS_SECRET)
        
        print(f"Checking latest successful build for {UPSTREAM_JOB}...")
        upstream_data = fetcher.get_upstream_build_data(UPSTREAM_JOB)
        
        if not is_build_recent(int(upstream_data["timestamp"])):
            print("The build job is older than 24 hours, discarding.")
            return

        print(f"Querying downstream job {DOWNSTREAM_JOB} for matching criteria...")
        build_params = fetcher.get_downstream_build_params(
            downstream_job=DOWNSTREAM_JOB,
            upstream_job=UPSTREAM_JOB,
            upstream_id=upstream_data["id"],
            platform=PLATFORM,
            deploy_type=DEPLOY_TYPE
        )
        
        # Put your actual code utilizing branch and commit in here:
        print(f"Targeting Branch: {build_params['BRANCH']}")
        print(f"Targeting Commit Hash: {build_params['COMMIT']}")

    except requests.exceptions.RequestException as req_err:
        print(f"Network dependency failure: {req_err}")
    except (KeyError, ValueError, ET.ParseError) as data_err:
        print(f"Data processing failure: {data_err}")


if __name__ == "__main__":
    main()
