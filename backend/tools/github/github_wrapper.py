"""Util that calls GitHub."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import requests
import re
from langchain_core.utils import get_from_dict_or_env
from pydantic import BaseModel, ConfigDict, model_validator

if TYPE_CHECKING:
    from github.Issue import Issue
    from github.PullRequest import PullRequest


def _import_tiktoken() -> Any:
    """Import tiktoken."""
    try:
        import tiktoken
    except ImportError:
        raise ImportError(
            "tiktoken is not installed. "
            "Please install it with `pip install tiktoken`"
        )
    return tiktoken




class GitHubAPIWrapper(BaseModel):
    """Wrapper for GitHub API."""

    github: Any = None  #: :meta private:
    github_repo_instance: Any = None  #: :meta private:
    github_repository: Optional[str] = None
    github_token: Optional[str] = None
    github_username: Optional[str] = None
    #github_password: Optional[str] = None
    active_branch: Optional[str] = None
    github_base_branch: Optional[str] = None

    model_config = ConfigDict(
        extra="forbid",
    )

    @model_validator(mode="before")
    @classmethod
    def validate_environment(cls, values: Dict) -> Any:
        """Validate that api key and python package exists in environment."""
        github_repository = get_from_dict_or_env(
            values, "github_repository", "GITHUB_REPOSITORY"
        )

        # Get authentication details (multiple options supported)
        github_token = get_from_dict_or_env(values, "github_token", "GITHUB_TOKEN", default=None)
        github_username = get_from_dict_or_env(values, "github_username", "GITHUB_USERNAME", default=None)
        #github_password = get_from_dict_or_env(values, "github_password", "GITHUB_PASSWORD", default=None)
        github_repository = get_from_dict_or_env(values, "github_repository", "GITHUB_REPOSITORY", default=None)

        try:
            from github import Github, Auth
        except ImportError:
            raise ImportError(
                "PyGithub is not installed. "
                "Please install it with `pip install PyGithub`"
            )

        # Initialize Github instance based on available credentials
        if github_token:
            # Prefer token authentication
            g = Github(github_token)
        #elif github_username and github_password:
            # Fallback to username/password
          #  g = Github(github_username, github_password)
        else:
            raise ValueError(
                "Please provide either GITHUB_TOKEN or both GITHUB_USERNAME and GITHUB_PASSWORD"
            )

        try:
            # Test authentication and get repo
            repo = g.get_repo(github_repository)
            
            # Get default branch settings
            github_base_branch = get_from_dict_or_env(
                values,
                "github_base_branch",
                "GITHUB_BASE_BRANCH",
                default=repo.default_branch,
            )

            active_branch = get_from_dict_or_env(
                values,
                "active_branch",
                "ACTIVE_BRANCH",
                default=repo.default_branch,
            )

            # Update values dictionary
            values["github"] = g
            values["github_repo_instance"] = repo
            values["github_repository"] = github_repository
            values["active_branch"] = active_branch
            values["github_base_branch"] = github_base_branch

            return values

        except Exception as e:
            raise ValueError(f"GitHub authentication failed: {str(e)}")



    def parse_issues(self, issues: List[Issue]) -> List[dict]:
        """
        Extracts title and number from each Issue and puts them in a dictionary
        Parameters:
            issues(List[Issue]): A list of Github Issue objects
        Returns:
            List[dict]: A dictionary of issue titles and numbers
        """
        parsed = []
        for issue in issues:
            title = issue.title
            number = issue.number
            opened_by = issue.user.login if issue.user else None
            issue_dict = {"title": title, "number": number}
            if opened_by is not None:
                issue_dict["opened_by"] = opened_by
            parsed.append(issue_dict)
        return parsed




    def parse_pull_requests(self, pull_requests: List[PullRequest]) -> List[dict]:
        """
        Extracts title and number from each Issue and puts them in a dictionary
        Parameters:
            issues(List[Issue]): A list of Github Issue objects
        Returns:
            List[dict]: A dictionary of issue titles and numbers
        """
        parsed = []
        for pr in pull_requests:
            parsed.append(
                {
                    "title": pr.title,
                    "number": pr.number,
                    "commits": str(pr.commits),
                    "comments": str(pr.comments),
                }
            )
        return parsed




    def get_issues(self) -> str:
        """
        Fetches all open issues from the repo excluding pull requests

        Returns:
            str: A plaintext report containing the number of issues
            and each issue's title and number.
        """
        issues = self.github_repo_instance.get_issues(state="open")
        # Filter out pull requests (part of GH issues object)
        issues = [issue for issue in issues if not issue.pull_request]
        if issues:
            parsed_issues = self.parse_issues(issues)
            parsed_issues_str = (
                "Found " + str(len(parsed_issues)) + " issues:\n" + str(parsed_issues)
            )
            return parsed_issues_str
        else:
            return "No open issues available"




    def list_open_pull_requests(self) -> str:
        """
        Fetches all open PRs from the repo

        Returns:
            str: A plaintext report containing the number of PRs
            and each PR's title and number.
        """
        # issues = self.github_repo_instance.get_issues(state="open")
        pull_requests = self.github_repo_instance.get_pulls(state="open")
        if pull_requests.totalCount > 0:
            parsed_prs = self.parse_pull_requests(pull_requests)
            parsed_prs_str = (
                "Found " + str(len(parsed_prs)) + " pull requests:\n" + str(parsed_prs)
            )
            return parsed_prs_str
        else:
            return "No open pull requests available"




    def list_files_in_main_branch(self) -> str:
        """
        List all files in the main branch of the repository
        
        Returns:
            str: Newline-separated list of files
        """
        try:
            # Get the repository contents
            contents = self.github_repo_instance.get_contents("")
            
            # Function to recursively list files
            def list_files_recursive(contents_list, path=""):
                file_list = []
                for content in contents_list:
                    if content.type == "dir":
                        # Recursively list files in subdirectories
                        file_list.extend(
                            list_files_recursive(
                                self.github_repo_instance.get_contents(content.path), 
                                path=content.path
                            )
                        )
                    elif content.type == "file":
                        # Add file path to the list
                        file_list.append(content.path)
                return file_list
            
            # Get all files
            all_files = list_files_recursive(contents)
            
            # Prepare the output string
            output = f"{len(all_files)}\n" + "\n".join(all_files)
            
            return output
        
        except Exception as e:
            print(f"Error listing repository files: {str(e)}")
            return f"0\nError: {str(e)}"




    def set_active_branch(self, branch_name: str) -> str:
        """Equivalent to `git checkout branch_name` for this Agent.
        Clones formatting from Github.

        Returns an Error (as a string) if branch doesn't exist.
        """
        curr_branches = [
            branch.name for branch in self.github_repo_instance.get_branches()
        ]
        if branch_name in curr_branches:
            self.active_branch = branch_name
            return f"Switched to branch `{branch_name}`"
        else:
            return (
                f"Error {branch_name} does not exist,"
                f"in repo with current branches: {str(curr_branches)}"
            )




    def list_branches_in_repo(self) -> str:
        """
        Fetches a list of all branches in the repository.

        Returns:
            str: A plaintext report containing the names of the branches.
        """
        try:
            branches = [
                branch.name for branch in self.github_repo_instance.get_branches()
            ]
            if branches:
                branches_str = "\n".join(branches)
                return (
                    f"Found {len(branches)} branches in the repository:"
                    f"\n{branches_str}"
                )
            else:
                return "No branches found in the repository"
        except Exception as e:
            return str(e)




    def create_branch(self, proposed_branch_name: str) -> str:
        """
        Create a new branch, and set it as the active bot branch.
        Equivalent to `git switch -c proposed_branch_name`
        If the proposed branch already exists, we append _v1 then _v2...
        until a unique name is found.

        Returns:
            str: A plaintext success message.
        """
        from github import GithubException

        i = 0
        new_branch_name = proposed_branch_name
        base_branch = self.github_repo_instance.get_branch(
            self.github_repo_instance.default_branch
        )
        for i in range(1000):
            try:
                self.github_repo_instance.create_git_ref(
                    ref=f"refs/heads/{new_branch_name}", sha=base_branch.commit.sha
                )
                self.active_branch = new_branch_name
                return (
                    f"Branch '{new_branch_name}' "
                    "created successfully, and set as current active branch."
                )
            except GithubException as e:
                if e.status == 422 and "Reference already exists" in e.data["message"]:
                    i += 1
                    new_branch_name = f"{proposed_branch_name}_v{i}"
                else:
                    # Handle any other exceptions
                    print(f"Failed to create branch. Error: {e}")  # noqa: T201
                    raise Exception(
                        "Unable to create branch name from proposed_branch_name: "
                        f"{proposed_branch_name}"
                    )
        return (
            "Unable to create branch. "
            "At least 1000 branches exist with named derived from "
            f"proposed_branch_name: `{proposed_branch_name}`"
        )




    def list_files_in_bot_branch(self) -> str:
        """
        Fetches all files in the active branch of the repo,
        the branch the bot uses to make changes.

        Returns:
            str: A plaintext list containing the filepaths in the branch.
        """
        files: List[str] = []
        try:
            contents = self.github_repo_instance.get_contents(
                "", ref=self.active_branch
            )
            for content in contents:
                if content.type == "dir":
                    files.extend(self.get_files_from_directory(content.path))
                else:
                    files.append(content.path)

            if files:
                files_str = "\n".join(files)
                return (
                    f"Found {len(files)} files in branch `{self.active_branch}`:\n"
                    f"{files_str}"
                )
            else:
                return f"No files found in branch: `{self.active_branch}`"
        except Exception as e:
            return f"Error: {e}"




    def get_files_from_directory(self, directory_path: str) -> str:
        """
        Recursively fetches files from a directory in the repo.

        Parameters:
            directory_path (str): Path to the directory

        Returns:
            str: List of file paths, or an error message.
        """
        from github import GithubException

        files: List[str] = []
        try:
            contents = self.github_repo_instance.get_contents(
                directory_path, ref=self.active_branch
            )
        except GithubException as e:
            return f"Error: status code {e.status}, {e.message}"

        for content in contents:
            if content.type == "dir":
                files.extend(self.get_files_from_directory(content.path))
            else:
                files.append(content.path)
        return str(files)




    def get_issue(self, issue_number: int) -> Dict[str, Any]:
        """
        Fetches a specific issue and its first 10 comments
        Parameters:
            issue_number(int): The number for the github issue
        Returns:
            dict: A dictionary containing the issue's title,
            body, comments as a string, and the username of the user
            who opened the issue
        """
        issue = self.github_repo_instance.get_issue(number=issue_number)
        page = 0
        comments: List[dict] = []
        while len(comments) <= 10:
            comments_page = issue.get_comments().get_page(page)
            if len(comments_page) == 0:
                break
            for comment in comments_page:
                comments.append({"body": comment.body, "user": comment.user.login})
            page += 1

        opened_by = None
        if issue.user and issue.user.login:
            opened_by = issue.user.login

        return {
            "number": issue_number,
            "title": issue.title,
            "body": issue.body,
            "comments": str(comments),
            "opened_by": str(opened_by),
        }




    def list_pull_request_files(self, pr_number: int) -> List[Dict[str, Any]]:
        """Fetches the full text of all files in a PR. Truncates after first 3k tokens.
        # TODO: Enhancement to summarize files with ctags if they're getting long.

        Args:
            pr_number(int): The number of the pull request on Github

        Returns:
            dict: A dictionary containing the issue's title,
            body, and comments as a string
        """
        tiktoken = _import_tiktoken()
        MAX_TOKENS_FOR_FILES = 3_000
        pr_files = []
        pr = self.github_repo_instance.get_pull(number=int(pr_number))
        total_tokens = 0
        page = 0
        while True:  # or while (total_tokens + tiktoken()) < MAX_TOKENS_FOR_FILES:
            files_page = pr.get_files().get_page(page)
            if len(files_page) == 0:
                break
            for file in files_page:
                try:
                    file_metadata_response = requests.get(file.contents_url)
                    if file_metadata_response.status_code == 200:
                        download_url = json.loads(file_metadata_response.text)[
                            "download_url"
                        ]
                    else:
                        print(f"Failed to download file: {file.contents_url}, skipping")  # noqa: T201
                        continue

                    file_content_response = requests.get(download_url)
                    if file_content_response.status_code == 200:
                        # Save the content as a UTF-8 string
                        file_content = file_content_response.text
                    else:
                        print(  # noqa: T201
                            "Failed downloading file content "
                            f"(Error {file_content_response.status_code}). Skipping"
                        )
                        continue

                    file_tokens = len(
                        tiktoken.get_encoding("cl100k_base").encode(
                            file_content + file.filename + "file_name file_contents"
                        )
                    )
                    if (total_tokens + file_tokens) < MAX_TOKENS_FOR_FILES:
                        pr_files.append(
                            {
                                "filename": file.filename,
                                "contents": file_content,
                                "additions": file.additions,
                                "deletions": file.deletions,
                            }
                        )
                        total_tokens += file_tokens
                except Exception as e:
                    print(f"Error when reading files from a PR on github. {e}")  # noqa: T201
            page += 1
        return pr_files




    def get_pull_request(self, pr_number: int) -> Dict[str, Any]:
        """
        Fetches a specific pull request and its first 10 comments,
        limited by max_tokens.

        Parameters:
            pr_number(int): The number for the Github pull
            max_tokens(int): The maximum number of tokens in the response
        Returns:
            dict: A dictionary containing the pull's title, body,
            and comments as a string
        """
        max_tokens = 2_000
        pull = self.github_repo_instance.get_pull(number=pr_number)
        total_tokens = 0

        def get_tokens(text: str) -> int:
            tiktoken = _import_tiktoken()
            return len(tiktoken.get_encoding("cl100k_base").encode(text))

        def add_to_dict(data_dict: Dict[str, Any], key: str, value: str) -> None:
            nonlocal total_tokens  # Declare total_tokens as nonlocal
            tokens = get_tokens(value)
            if total_tokens + tokens <= max_tokens:
                data_dict[key] = value
                total_tokens += tokens  # Now this will modify the outer variable

        response_dict: Dict[str, str] = {}
        add_to_dict(response_dict, "title", pull.title)
        add_to_dict(response_dict, "number", str(pr_number))
        add_to_dict(response_dict, "body", pull.body if pull.body else "")

        comments: List[str] = []
        page = 0
        while len(comments) <= 10:
            comments_page = pull.get_issue_comments().get_page(page)
            if len(comments_page) == 0:
                break
            for comment in comments_page:
                comment_str = str({"body": comment.body, "user": comment.user.login})
                if total_tokens + get_tokens(comment_str) > max_tokens:
                    break
                comments.append(comment_str)
                total_tokens += get_tokens(comment_str)
            page += 1
        add_to_dict(response_dict, "comments", str(comments))

        commits: List[str] = []
        page = 0
        while len(commits) <= 10:
            commits_page = pull.get_commits().get_page(page)
            if len(commits_page) == 0:
                break
            for commit in commits_page:
                commit_str = str({"message": commit.commit.message})
                if total_tokens + get_tokens(commit_str) > max_tokens:
                    break
                commits.append(commit_str)
                total_tokens += get_tokens(commit_str)
            page += 1
        add_to_dict(response_dict, "commits", str(commits))
        return response_dict




    def create_pull_request(self, pr_query: str) -> str:
        """
        Makes a pull request from the bot's branch to the base branch
        Parameters:
            pr_query(str): a string which contains the PR title
            and the PR body. The title is the first line
            in the string, and the body are the rest of the string.
            For example, "Updated README\nmade changes to add info"
        Returns:
            str: A success or failure message
        """
        if self.github_base_branch == self.active_branch:
            return """Cannot make a pull request because 
            commits are already in the main or master branch."""
        else:
            try:
                title = pr_query.split("\n")[0]
                body = pr_query[len(title) + 2 :]
                pr = self.github_repo_instance.create_pull(
                    title=title,
                    body=body,
                    head=self.active_branch,
                    base=self.github_base_branch,
                )
                return f"Successfully created PR number {pr.number}"
            except Exception as e:
                return "Unable to make pull request due to error:\n" + str(e)




    def comment_on_issue(self, comment_query: str) -> str:
        """
        Adds a comment to a github issue
        Parameters:
            comment_query(str): a string which contains the issue number,
            two newlines, and the comment.
            for example: "1\n\nWorking on it now"
            adds the comment "working on it now" to issue 1
        Returns:
            str: A success or failure message
        """
        issue_number = int(comment_query.split("\n\n")[0])
        comment = comment_query[len(str(issue_number)) + 2 :]
        try:
            issue = self.github_repo_instance.get_issue(number=issue_number)
            issue.create_comment(comment)
            return "Commented on issue " + str(issue_number)
        except Exception as e:
            return "Unable to make comment due to error:\n" + str(e)




    def create_file(self, file_query: str) -> str:
        """
        Creates a new file on the Github repo
        Parameters:
            file_query(str): a string which contains the file path
            and the file contents. The file path is the first line
            in the string, and the contents are the rest of the string.
            For example, "hello_world.md\n# Hello World!"
        Returns:
            str: A success or failure message
        """
        if self.active_branch == self.github_base_branch:
            return (
                "You're attempting to commit to the directly to the"
                f"{self.github_base_branch} branch, which is protected. "
                "Please create a new branch and try again."
            )

        file_path = file_query.split("\n")[0]
        file_contents = file_query[len(file_path) + 2 :]

        try:
            try:
                file = self.github_repo_instance.get_contents(
                    file_path, ref=self.active_branch
                )
                if file:
                    return (
                        f"File already exists at `{file_path}` "
                        f"on branch `{self.active_branch}`. You must use "
                        "`update_file` to modify it."
                    )
            except Exception:
                # expected behavior, file shouldn't exist yet
                pass

            self.github_repo_instance.create_file(
                path=file_path,
                message="Create " + file_path,
                content=file_contents,
                branch=self.active_branch,
            )
            return "Created file " + file_path
        except Exception as e:
            return "Unable to make file due to error:\n" + str(e)




    def read_file(self, file_path: str) -> str:
        """
        Read a file from this agent's branch, defined by self.active_branch,
        which supports PR branches.
        Parameters:
            file_path(str): the file path
        Returns:
            str: The file decoded as a string, or an error message if not found
        """
        try:
            file = self.github_repo_instance.get_contents(
                file_path, ref=self.active_branch
            )
            return file.decoded_content.decode("utf-8")
        except Exception as e:
            return (
                f"File not found `{file_path}` on branch"
                f"`{self.active_branch}`. Error: {str(e)}"
            )




    def update_file(self, file_query: str) -> str:
        """
        Updates a file with new content.
        Parameters:
            file_query(str): Contains the file path and the file contents.
                The old file contents is wrapped in OLD <<<< and >>>> OLD
                The new file contents is wrapped in NEW <<<< and >>>> NEW
                For example:
                /test/hello.txt
                OLD <<<<
                Hello Earth!
                >>>> OLD
                NEW <<<<
                Hello Mars!
                >>>> NEW
        Returns:
            A success or failure message
        """
        if self.active_branch == self.github_base_branch:
            return (
                "You're attempting to commit to the directly"
                f"to the {self.github_base_branch} branch, which is protected. "
                "Please create a new branch and try again."
            )
        try:
            file_path: str = file_query.split("\n")[0]
            old_file_contents = (
                file_query.split("OLD <<<<")[1].split(">>>> OLD")[0].strip()
            )
            new_file_contents = (
                file_query.split("NEW <<<<")[1].split(">>>> NEW")[0].strip()
            )

            file_content = self.read_file(file_path)
            updated_file_content = file_content.replace(
                old_file_contents, new_file_contents
            )

            if file_content == updated_file_content:
                return (
                    "File content was not updated because old content was not found."
                    "It may be helpful to use the read_file action to get "
                    "the current file contents."
                )

            self.github_repo_instance.update_file(
                path=file_path,
                message="Update " + str(file_path),
                content=updated_file_content,
                branch=self.active_branch,
                sha=self.github_repo_instance.get_contents(
                    file_path, ref=self.active_branch
                ).sha,
            )
            return "Updated file " + str(file_path)
        except Exception as e:
            return "Unable to update file due to error:\n" + str(e)




    def delete_file(self, file_path: str) -> str:
        """
        Deletes a file from the repo
        Parameters:
            file_path(str): Where the file is
        Returns:
            str: Success or failure message
        """
        if self.active_branch == self.github_base_branch:
            return (
                "You're attempting to commit to the directly"
                f"to the {self.github_base_branch} branch, which is protected. "
                "Please create a new branch and try again."
            )
        try:
            self.github_repo_instance.delete_file(
                path=file_path,
                message="Delete " + file_path,
                branch=self.active_branch,
                sha=self.github_repo_instance.get_contents(
                    file_path, ref=self.active_branch
                ).sha,
            )
            return "Deleted file " + file_path
        except Exception as e:
            return "Unable to delete file due to error:\n" + str(e)




    def search_issues_and_prs(self, query: str) -> str:
        """
        Searches issues and pull requests in the repository.

        Parameters:
            query(str): The search query

        Returns:
            str: A string containing the first 5 issues and pull requests
        """
        search_result = self.github.search_issues(query, repo=self.github_repository)
        max_items = min(5, search_result.totalCount)
        results = [f"Top {max_items} results:"]
        for issue in search_result[:max_items]:
            results.append(
                f"Title: {issue.title}, Number: {issue.number}, State: {issue.state}"
            )
        return "\n".join(results)




    def search_code(self, query: str) -> str:
        """
        Searches code in the repository.
        # Todo: limit total tokens returned...

        Parameters:
            query(str): The search query

        Returns:
            str: A string containing, at most, the top 5 search results
        """
        search_result = self.github.search_code(
            query=query, repo=self.github_repository
        )
        if search_result.totalCount == 0:
            return "0 results found."
        max_results = min(5, search_result.totalCount)
        results = [f"Showing top {max_results} of {search_result.totalCount} results:"]
        count = 0
        for code in search_result:
            if count >= max_results:
                break
            # Get the file content using the PyGithub get_contents method
            file_content = self.github_repo_instance.get_contents(
                code.path, ref=self.active_branch
            ).decoded_content.decode()
            results.append(
                f"Filepath: `{code.path}`\nFile contents: "
                f"{file_content}\n<END OF FILE>"
            )
            count += 1
        return "\n".join(results)




    def create_review_request(self, reviewer_username: str) -> str:
        """
        Creates a review request on *THE* open pull request
        that matches the current active_branch.

        Parameters:
            reviewer_username(str): The username of the person who is being requested

        Returns:
            str: A message confirming the creation of the review request
        """
        pull_requests = self.github_repo_instance.get_pulls(
            state="open", sort="created"
        )
        # find PR against active_branch
        pr = next(
            (pr for pr in pull_requests if pr.head.ref == self.active_branch), None
        )
        if pr is None:
            return (
                "No open pull request found for the "
                f"current branch `{self.active_branch}`"
            )

        try:
            pr.create_review_request(reviewers=[reviewer_username])
            return (
                f"Review request created for user {reviewer_username} "
                f"on PR #{pr.number}"
            )
        except Exception as e:
            return f"Failed to create a review request with error {e}"

    def get_file_content_with_lines(self, file_path: str) -> Dict[str, Any]:
        """
        Get file content with line numbers and metadata.
        
        Args:
            file_path (str): Path to the file
            
        Returns:
            Dict with file content, line count, and metadata
        """
        try:
            file_content = self.github_repo_instance.get_contents(
                file_path, ref=self.active_branch
            )
            content = file_content.decoded_content.decode()
            lines = content.split('\n')
            return {
                "content": content,
                "lines": lines,
                "line_count": len(lines),
                "sha": file_content.sha,
                "path": file_path
            }
        except Exception as e:
            return {"error": f"Failed to get file content: {str(e)}"}




    def update_file_lines(self, file_path: str, line_updates: Dict[str, Any]) -> str:
        """
        Update specific lines in a file.
        
        Args:
            file_path (str): Path to the file
            line_updates (Dict[str, Any]): Dictionary containing:
                - start_line: Starting line number
                - end_line: Ending line number
                - new_content: New content to insert
                - commit_message: Commit message
                
        Returns:
            str: Result message
        """
        try:
            file_info = self.get_file_content_with_lines(file_path)
            if "error" in file_info:
                return file_info["error"]
            
            lines = file_info["lines"]
            start_line = line_updates["start_line"] - 1  # Convert to 0-based index
            end_line = line_updates["end_line"] - 1
            
            if start_line < 0 or end_line >= len(lines):
                return f"Invalid line range: file has {len(lines)} lines"
            
            # Replace the specified lines
            lines[start_line:end_line + 1] = line_updates["new_content"].split('\n')
            
            # Create the updated content
            updated_content = '\n'.join(lines)
            
            # Commit the changes
            self.github_repo_instance.update_file(
                file_path,
                line_updates["commit_message"],
                updated_content,
                file_info["sha"],
                branch=self.active_branch
            )
            
            return f"Successfully updated lines {start_line + 1} to {end_line + 1} in {file_path}"
        except Exception as e:
            return f"Failed to update file: {str(e)}"

    def resolve_file_path(self, error_path: str) -> str:
        """
        Resolve the actual file path in the repository from an error path.
        
        Args:
            error_path (str): Path from error message (e.g., /opt/airflow/includes/...)
            
        Returns:
            str: Resolved path in the repository or error message
        """
        # Remove common prefixes that appear in error paths
        common_prefixes = ['/opt/airflow/', '/home/airflow/', '/usr/local/']
        clean_path = error_path
        for prefix in common_prefixes:
            if clean_path.startswith(prefix):
                clean_path = clean_path[len(prefix):]
        
        # Generate possible path variations
        path_variations = [
            clean_path,
            '/'.join(clean_path.split('/')[1:]),  # Remove first directory
            '/'.join(clean_path.split('/')[-3:])  # Take last 3 path components
        ]
        
        try:
            # Get all files in the repository
            all_files = []
            contents = self.github_repo_instance.get_contents("", ref=self.active_branch)
            while contents:
                file_content = contents.pop(0)
                if file_content.type == "dir":
                    contents.extend(self.github_repo_instance.get_contents(file_content.path, ref=self.active_branch))
                else:
                    all_files.append(file_content.path)
            
            # Try to find exact match first
            for path in path_variations:
                if path in all_files:
                    return path
            
            # If no exact match, try fuzzy matching
            for path in path_variations:
                for repo_path in all_files:
                    if path.split('/')[-1] in repo_path and all(
                        component in repo_path for component in path.split('/')[-3:-1]
                    ):
                        return repo_path
            
            return f"Could not resolve path. Tried variations: {', '.join(path_variations)}"
        except Exception as e:
            return f"Error resolving path: {str(e)}"
    
    def resolve_error_path(self, error_path: str) -> str:
        """
        Resolve the actual file path from an error path.
        
        Args:
            error_path (str): Path from error message
            
        Returns:
            str: Resolved path in the repository
        """
        return self.github.resolve_file_path(error_path)
    

    def analyze_imports(self, file_content: str) -> List[Dict[str, str]]:
        """
        Analyze Python imports in a file and resolve their paths.
        
        Args:
            file_content (str): Content of the Python file
            
        Returns:
            List[Dict[str, str]]: List of resolved import information
        """
        import_patterns = [
            r'^from\s+([\w.]+)\s+import\s+(.+)$',  # from x.y.z import a
            r'^import\s+([\w.]+)(?:\s+as\s+\w+)?$'  # import x.y.z
        ]
        
        imports = []
        for line in file_content.split('\n'):
            line = line.strip()
            for pattern in import_patterns:
                match = re.match(pattern, line)
                if match:
                    module_path = match.group(1)
                    # Convert dot notation to directory structure
                    file_path = module_path.replace('.', '/') + '.py'
                    resolved_path = self.resolve_file_path(file_path)
                    
                    imports.append({
                        "original_import": line,
                        "module_path": module_path,
                        "resolved_path": resolved_path,
                        "imported_items": match.group(2) if len(match.groups()) > 1 else None
                    })
                    break
        
        return imports

    def get_dependency_tree(self, file_path: str, max_depth: int = 3) -> Dict[str, Any]:
        """
        Build a dependency tree for a given file.
        
        Args:
            file_path (str): Starting file path
            max_depth (int): Maximum depth for dependency resolution
            
        Returns:
            Dict[str, Any]: Dependency tree structure
        """
        try:
            content = self.get_file_content_with_lines(file_path)
            if "error" in content:
                return {"error": content["error"]}
            
            imports = self.analyze_imports(content["content"])
            
            tree = {
                "file_path": file_path,
                "content": content,
                "imports": imports,
                "dependencies": {}
            }
            
            if max_depth > 0:
                for imp in imports:
                    if imp["resolved_path"] and imp["resolved_path"].endswith('.py'):
                        tree["dependencies"][imp["resolved_path"]] = self.get_dependency_tree(
                            imp["resolved_path"], 
                            max_depth - 1
                        )
                        
            return tree
        except Exception as e:
            return {"error": f"Failed to build dependency tree: {str(e)}"}

    def get_file_history(self, file_path: str) -> List[Dict[str, Any]]:
        """Get detailed commit history for a specific file."""
        try:
            # Try different path variations
            path_variations = [
                file_path,
                f"airflow/includes/{file_path}",
                f"airflow/{file_path}",
                file_path.replace('includes/', ''),
                file_path.replace('airflow/', ''),
                file_path.replace('airflow/includes/', '')
            ]
            
            for try_path in path_variations:
                try:
                    print(f"🔍 Trying path: {try_path}")
                    commits = self.github_repo_instance.get_commits(path=try_path)
                    
                    if commits and commits.totalCount > 0:
                        print(f"✅ Found commits using path: {try_path}")
                        history = []
                        
                        for commit in commits:
                            try:
                                file_change = None
                                for file in commit.files:
                                    # Check if the file matches any of our path variations
                                    if any(variation in file.filename for variation in path_variations):
                                        file_change = file
                                        break
                                
                                if file_change:
                                    history.append({
                                        "sha": commit.sha,
                                        "date": commit.commit.author.date.isoformat(),
                                        "message": commit.commit.message,
                                        "author": commit.commit.author.name,
                                        "changes": {
                                            "additions": file_change.additions,
                                            "deletions": file_change.deletions,
                                            "changes": file_change.changes,
                                            "status": file_change.status
                                        }
                                    })
                            except Exception as commit_error:
                                print(f"Error processing commit {commit.sha}: {str(commit_error)}")
                                continue
                        
                        if history:
                            return history
                except Exception as path_error:
                    print(f"Error trying path {try_path}: {str(path_error)}")
                    continue
            
            print(f"No valid commits found for any path variation")
            return []
            
        except Exception as e:
            print(f"Error in get_file_history: {str(e)}")
            return []

    def generate_comparison_url(self, base_commit: str, head_commit: str, file_path: str) -> str:
        """Generate a GitHub comparison URL for file changes."""
        try:
            repo_name = self.github_repository
            return f"https://github.com/{repo_name}/compare/{base_commit}...{head_commit}?diff=split#{file_path}"
        except Exception as e:
            return f"Error generating comparison URL: {str(e)}"

    def get_file_content_at_commit(self, file_path: str, commit_sha: str) -> Dict[str, Any]:
        """Get file content at a specific commit with detailed metadata."""
        try:
            # Normalize file path
            file_path = file_path.lstrip('/')
            
            # Get the specific commit
            commit = self.github_repo_instance.get_commit(commit_sha)
            
            # Find the file in the commit
            file_change = next(
                (f for f in commit.files if f.filename == file_path),
                None
            )
            
            if not file_change:
                return {
                    "error": f"File {file_path} not found in commit {commit_sha}",
                    "content": ""
                }
            
            # Get the file content
            content = self.github_repo_instance.get_contents(file_path, ref=commit_sha)
            
            return {
                "content": content.decoded_content.decode('utf-8'),
                "sha": commit_sha,
                "metadata": {
                    "additions": file_change.additions,
                    "deletions": file_change.deletions,
                    "changes": file_change.changes,
                    "status": file_change.status
                }
            }
        except Exception as e:
            print(f"Error getting file content: {str(e)}")
            return {"error": str(e), "content": ""}

    def run(self, mode: str, query: str, **kwargs) -> str:
        if mode == "get_issue":
            return json.dumps(self.get_issue(int(query)))
        elif mode == "get_pull_request":
            return json.dumps(self.get_pull_request(int(query)))
        elif mode == "list_pull_request_files":
            return json.dumps(self.list_pull_request_files(int(query)))
        elif mode == "get_issues":
            return self.get_issues()
        elif mode == "comment_on_issue":
            return self.comment_on_issue(query)
        elif mode == "create_file":
            return self.create_file(query)
        elif mode == "create_pull_request":
            return self.create_pull_request(query)
        elif mode == "read_file":
            return self.read_file(query)
        elif mode == "update_file":
            return self.update_file(query)
        elif mode == "delete_file":
            return self.delete_file(query)
        elif mode == "list_open_pull_requests":
            return self.list_open_pull_requests()
        elif mode == "list_files_in_main_branch":
            return self.list_files_in_main_branch()
        elif mode == "list_files_in_bot_branch":
            return self.list_files_in_bot_branch()
        elif mode == "list_branches_in_repo":
            return self.list_branches_in_repo()
        elif mode == "set_active_branch":
            return self.set_active_branch(query)
        elif mode == "create_branch":
            return self.create_branch(query)
        elif mode == "get_files_from_directory":
            return self.get_files_from_directory(query)
        elif mode == "search_issues_and_prs":
            return self.search_issues_and_prs(query)
        elif mode == "search_code":
            return self.search_code(query)
        elif mode == "create_review_request":
            return self.create_review_request(query)
        elif mode == "update_file_lines":
            update_info = json.loads(query)
            return self.update_file_lines(update_info["file_path"], update_info)
        elif mode == "get_file_content_with_lines":
            file_info = json.loads(query)
            return json.dumps(self.get_file_content_with_lines(file_info["file_path"]))
        elif mode == "resolve_file_path":
            return self.resolve_file_path(query)
        if mode == "analyze_file_changes":

            return self.api_wrapper.analyze_file_changes(
                kwargs.get('old_content', ''), 
                kwargs.get('new_content', '')
            )
        elif mode == "generate_code_snippet":
            return self.api_wrapper.generate_code_snippet(
                kwargs.get('old_content', ''), 
                kwargs.get('new_content', ''),
                kwargs.get('changes')
            )
        elif mode == "generate_comprehensive_summary":
            return self.api_wrapper.generate_comprehensive_summary(
                kwargs.get('file_path', ''),
                kwargs.get('last_commit', {}),
                kwargs.get('previous_commit', {}),
                kwargs.get('changes', {}),
                kwargs.get('code_snippet', {})
            )
        else:
            raise ValueError("Invalid mode" + mode)

    def analyze_file_changes(self, old_content: str, new_content: str) -> Dict[str, Any]:
        """
        Analyze changes between two file versions with detailed context
        """
        from difflib import SequenceMatcher
        
        # Normalize contents
        old_lines = old_content.splitlines() if isinstance(old_content, str) else []
        new_lines = new_content.splitlines() if isinstance(new_content, str) else []
        
        # Use SequenceMatcher for intelligent diff
        matcher = SequenceMatcher(None, old_lines, new_lines)
        
        # Initialize changes dictionary
        changes = {
            'additions': 0,
            'deletions': 0,
            'modifications': 0,
            'added': [],
            'removed': [],
            'modified': [],
            'modified_context': []
        }
        
        # Analyze changes
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'replace':
                # Detailed modification tracking
                old_section = old_lines[i1:i2]
                new_section = new_lines[j1:j2]
                
                changes['modifications'] += len(new_section)
                changes['modified'].extend(new_section)
                
                # Capture modification context
                mod_context = {
                    'old_lines': old_section,
                    'new_lines': new_section,
                    'context_before': old_lines[max(0, i1-3):i1] if i1 > 0 else [],
                    'context_after': old_lines[i2:min(len(old_lines), i2+3)] if i2 < len(old_lines) else []
                }
                changes['modified_context'].append(mod_context)
            
            elif tag == 'delete':
                # Track deletions
                changes['deletions'] += i2 - i1
                changes['removed'].extend(old_lines[i1:i2])
            
            elif tag == 'insert':
                # Track additions
                changes['additions'] += j2 - j1
                changes['added'].extend(new_lines[j1:j2])
        
        return changes

    def generate_code_snippet(self, old_content: str, new_content: str, changes: Dict = None) -> Dict[str, Any]:
        """
        Generate a detailed code snippet highlighting the changes
        """
        snippet = {
            "added_lines": [],
            "removed_lines": [],
            "modified_lines": []
        }
        
        # Track added lines
        if changes.get('added'):
            snippet['added_lines'] = changes['added']
        
        # Track removed lines
        if changes.get('removed'):
            snippet['removed_lines'] = changes['removed']
        
        # Track modified lines with context
        if changes.get('modified_context'):
            for mod in changes['modified_context']:
                modified_info = {
                    'old_lines': mod['old_lines'],
                    'new_lines': mod['new_lines'],
                    'context_before': mod.get('context_before', []),
                    'context_after': mod.get('context_after', [])
                }
                snippet['modified_lines'].append(modified_info)
        
        return snippet

    def generate_comprehensive_summary(self, file_path: str, last_commit: Dict, 
                                       previous_commit: Dict, changes: Dict, 
                                       code_snippet: Dict) -> str:
        """
        Generate a comprehensive summary of file changes
        """
        # Basic change statistics
        additions = len(changes.get('added', []))
        deletions = len(changes.get('removed', []))
        modifications = len(changes.get('modified_context', []))
        
        # Commit details
        summary = f"Changes in {file_path}:\n\n"
        summary += "📊 Change Statistics:\n"
        summary += f"- Additions: {additions}\n"
        summary += f"- Deletions: {deletions}\n"
        summary += f"- Modifications: {modifications}\n\n"
        
        # Detailed change description
        summary += "🔍 Change Details:\n"
        
        # Added lines
        if additions > 0:
            summary += "✨ Added Lines:\n"
            for line in code_snippet.get('added_lines', []):
                summary += f"  + {line}\n"
            summary += "\n"
        
        # Removed lines
        if deletions > 0:
            summary += "🗑️ Removed Lines:\n"
            for line in code_snippet.get('removed_lines', []):
                summary += f"  - {line}\n"
            summary += "\n"
        
        # Modified lines
        if modifications > 0:
            summary += "📝 Modified Sections:\n"
            for mod in code_snippet.get('modified_lines', []):
                summary += "  Context Before:\n"
                for ctx in mod.get('context_before', []):
                    summary += f"    {ctx}\n"
                
                summary += "  Old Lines:\n"
                for old in mod.get('old_lines', []):
                    summary += f"  - {old}\n"
                
                summary += "  New Lines:\n"
                for new in mod.get('new_lines', []):
                    summary += f"  + {new}\n"
                
                summary += "  Context After:\n"
                for ctx in mod.get('context_after', []):
                    summary += f"    {ctx}\n"
                summary += "\n"
        
        # Commit information
        summary += "📋 Commit Information:\n"
        summary += f"Latest Commit: {last_commit['sha'][:7]} by {last_commit['author']} on {last_commit['date']}\n"
        summary += f"Previous Commit: {previous_commit['sha'][:7]} by {previous_commit['author']} on {previous_commit['date']}\n"
        
        return summary

    def get_file_content_at_commit(self, file_path: str, branch: str = None) -> Dict[str, Any]:
        """
        Get file content at a specific commit/branch
        
        Args:
            file_path (str): Path to the file
            branch (str, optional): Branch name. Defaults to base branch.
        
        Returns:
            Dict containing file content and metadata
        """
        try:
            # Use default branch if not specified
            if branch is None:
                branch = self.github_base_branch
            
            # Get file contents
            file_content = self.github_repo_instance.get_contents(file_path, ref=branch)
            
            # Decode content if it's base64 encoded
            decoded_content = file_content.decoded_content.decode('utf-8') if file_content.decoded_content else ''
            
            return {
                "content": decoded_content,
                "path": file_content.path,
                "sha": file_content.sha,
                "size": file_content.size,
                "encoding": file_content.encoding
            }
        
        except Exception as e:
            print(f"Error getting file content for {file_path}: {str(e)}")
            return {
                "content": "",
                "error": str(e),
                "path": file_path
            }









