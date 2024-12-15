import argparse
import os
import sys
import time

from icecream import ic
from src.checks import check_gh_token, is_org, prerequisites, repo_owner_verification
from src.exceptions import RepoOwnershipMixmatch
from src.gh import (
    auth,
    current_running_job_list,
    filter_job_list,
    follow_workflow_job,
    get_event_type_list_for_workflows,
    get_repository_dispatch,
    get_workflow_id,
    github,
)
from src.gh_api import GithubAPI

BASE = os.path.dirname(os.path.abspath(__file__))  # Get the base directory of the script

ic.disable()  # Disable icecream by default

parser = argparse.ArgumentParser(
    prog="sync-action-status",
    description="Syncs the status of a GitHub action to another repository.",
)

parser.add_argument(
    "--interval",
    type=str,
    required=False,
    help="The interval to poll the action for status.",
)
parser.add_argument(
    "--current_repo",
    dest="current_repo",
    type=str,
    required=True,
    help="The current repository calling the sync action.",
)
parser.add_argument(
    "--target_repo",
    dest="target_repo",
    type=str,
    required=True,
    help="The target repository to sync the status from.",
)
parser.add_argument(
    "--debug",
    action="store_true",
    required=False,
    default=False,
    help="Run in debug mode.",
)
parser.add_argument(
    "--event_type",
    dest="event_type",
    type=str,
    required=True,
    help="The event type to sync the status from.",
)

args = parser.parse_args()

# Enable debugging if the flag is passed
if args.debug:
    ic.enable()

# Ensure prerequisites are met
prerequisites(args)

# Ensure the repository ownership matches
if not repo_owner_verification(args):
    raise RepoOwnershipMixmatch(
        "The owner of the repository is not the same as the owner of the action."
    )

# Parse the GitHub actor and repository name
gh_actor_org = args.target_repo.split("/")[0]
repo_name = args.target_repo.split("/")[1]

# Determine if it's an organization or a user repository
if is_org(github_actor=gh_actor_org):
    args.is_org = True
    _api_data = f"orgs/{args.target_repo}"
    ic(f"GitHub Actor: {gh_actor_org} is an organization.")
else:
    args.is_org = False
    _api_data = f"repos/{args.target_repo}"
    ic(f"GitHub Actor: {gh_actor_org} is not an organization.")

# Set up the GitHub API connection
_gh_token = os.getenv("GH_TOKEN")
_api = GithubAPI(token=_gh_token, api_data=_api_data)

if __name__ == "__main__":
    check_gh_token(_gh_token)  # Check the GitHub token

    # Get the repository dispatch event details
    repo_dispatch = get_repository_dispatch(args=args)

    ic(f"Actor-Org: {gh_actor_org}")

    # Set up GitHub authentication and API connection
    auth = auth(gh_token=_gh_token)
    api = github(auth=auth)

    # Get event type data for workflows
    event_type_data = get_event_type_list_for_workflows(repo=repo_dispatch)
    ic(f"Event Type Data: {event_type_data}")

    # Filter the event types based on the passed event_type
    filtered_events = {}
    for _name, _event in event_type_data.items():
        if args.event_type in _event:
            print(f"Event Type: {args.event_type} found in {_event}")
            filtered_events[_name] = _event
        else:
            print(f"Event Type: {args.event_type} not found in {_event}")
            sys.exit(5)

    # If multiple workflows are found, handle them accordingly
    if len(filtered_events) > 1:
        print(f"Found multiple workflows for the event type {args.event_type}")
        sys.exit(5)

    # Handle the workflow synchronization if only one workflow is found
    if len(filtered_events) == 1:
        workflow_name = list(filtered_events.keys())[0]
        workflow_id = get_workflow_id(_name=workflow_name, repo=repo_dispatch)
        current_running_jobs = current_running_job_list(_name=workflow_name, repo=repo_dispatch)
        filtered_jobs = filter_job_list(current_running_jobs)
        _workflow_job_id = filtered_jobs["databaseId"]

        ic(f"Current Running Jobs: {current_running_jobs}")
        ic(f"Filtered Jobs: {filtered_jobs}")

        # Sync the status between the repositories
        print(f"Workflow Name: {workflow_name}")
        print(f"Workflow ID: {workflow_id}")
        print(f"Workflow Run ID: {_workflow_job_id}")

        # Poll the workflow run status until completion
        status = follow_workflow_job(
            workflow_job_id=_workflow_job_id, interval=args.interval, repo=repo_dispatch
        )

        # Once the status is fetched, synchronize it to the current repository
        print(f"Workflow Status: {status}")

        # Assuming the status is either "success" or "failure" for simplicity, you can extend this to handle more states.
        if status == "success":
            print("The workflow in the target repository was successful.")
            # You can trigger a success action on the current repository, e.g., creating a status check or updating an issue.
            # Example: Update a status in the current repository.
            # sync_status_to_current_repo(args.current_repo, "success")
        elif status == "failure":
            print("The workflow in the target repository failed.")
            # Handle failure case (e.g., create an issue, update status, etc.)
            # Example: Update a failure status in the current repository.
            # sync_status_to_current_repo(args.current_repo, "failure")

    else:
        print(f"Multiple event types {args.event_type} found -- Code changes needed to facilitate.")
        sys.exit(5)

    # Close the connection
    api.close()
