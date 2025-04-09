#!/usr/bin/env python
"""
Command-line utility for managing the GitHub repository storage
"""
import os
import sys
import argparse
import logging
from typing import List, Optional

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Import our repo manager
from utils import repo_manager

# Set up logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def list_repos(args):
    """List all repositories in the storage"""
    if not os.path.exists(repo_manager.REPO_STORAGE_BASE):
        print(f"Repository storage directory does not exist: {repo_manager.REPO_STORAGE_BASE}")
        return
    
    repo_dirs = []
    
    for dirname in os.listdir(repo_manager.REPO_STORAGE_BASE):
        repo_path = os.path.join(repo_manager.REPO_STORAGE_BASE, dirname)
        if os.path.isdir(repo_path) and os.path.exists(os.path.join(repo_path, '.git')):
            # Get basic info about the repo
            size = repo_manager.get_repository_size(repo_path)
            size_mb = size / (1024 * 1024)
            
            # Try to get the remote URL
            try:
                import subprocess
                result = subprocess.run(['git', '-C', repo_path, 'config', '--get', 'remote.origin.url'], 
                                        capture_output=True, text=True)
                url = result.stdout.strip() if result.returncode == 0 else "Unknown"
            except Exception:
                url = "Unknown"
            
            repo_dirs.append({
                'name': dirname,
                'path': repo_path,
                'size_mb': size_mb,
                'url': url,
                'last_accessed': os.path.getatime(repo_path)
            })
    
    if not repo_dirs:
        print("No repositories found in storage.")
        return
    
    # Sort by size
    if args.sort == 'size':
        repo_dirs.sort(key=lambda r: r['size_mb'], reverse=True)
    elif args.sort == 'name':
        repo_dirs.sort(key=lambda r: r['name'])
    elif args.sort == 'accessed':
        import time
        current_time = time.time()
        repo_dirs.sort(key=lambda r: current_time - r['last_accessed'])
    
    # Print header
    print(f"{'Repository':<50} {'Size (MB)':<10} {'Last Accessed':<20} {'URL':<50}")
    print("-" * 130)
    
    # Print each repository
    import datetime
    for repo in repo_dirs:
        last_accessed = datetime.datetime.fromtimestamp(repo['last_accessed']).strftime('%Y-%m-%d %H:%M:%S')
        print(f"{repo['name']:<50} {repo['size_mb']:<10.2f} {last_accessed:<20} {repo['url']:<50}")
    
    # Print total size
    total_size_mb = sum(repo['size_mb'] for repo in repo_dirs)
    total_size_gb = total_size_mb / 1024
    print("-" * 130)
    print(f"Total repositories: {len(repo_dirs)}")
    print(f"Total size: {total_size_mb:.2f} MB ({total_size_gb:.2f} GB)")

def clean_repos(args):
    """Clean up old repositories"""
    if not os.path.exists(repo_manager.REPO_STORAGE_BASE):
        print(f"Repository storage directory does not exist: {repo_manager.REPO_STORAGE_BASE}")
        return
    
    print(f"Cleaning repositories older than {args.days} days or exceeding {args.size} GB total...")
    repo_manager.clean_old_repositories(max_age_days=args.days, max_total_size_gb=args.size)
    print("Cleanup complete.")

def delete_repo(args):
    """Delete a specific repository"""
    if not args.name and not args.url:
        print("Error: Either --name or --url must be specified.")
        return
    
    if not os.path.exists(repo_manager.REPO_STORAGE_BASE):
        print(f"Repository storage directory does not exist: {repo_manager.REPO_STORAGE_BASE}")
        return
    
    # Get all repository directories
    found = False
    
    for dirname in os.listdir(repo_manager.REPO_STORAGE_BASE):
        repo_path = os.path.join(repo_manager.REPO_STORAGE_BASE, dirname)
        
        if not os.path.isdir(repo_path) or not os.path.exists(os.path.join(repo_path, '.git')):
            continue
        
        # Check if name matches
        if args.name and args.name.lower() in dirname.lower():
            confirm = input(f"Delete repository {dirname} at {repo_path}? (y/n): ")
            if confirm.lower() == 'y':
                import shutil
                shutil.rmtree(repo_path, ignore_errors=True)
                print(f"Deleted repository: {dirname}")
                found = True
            else:
                print(f"Skipped repository: {dirname}")
            continue
        
        # Check if URL matches
        if args.url:
            try:
                import subprocess
                result = subprocess.run(['git', '-C', repo_path, 'config', '--get', 'remote.origin.url'], 
                                        capture_output=True, text=True)
                if result.returncode == 0 and args.url.lower() in result.stdout.strip().lower():
                    confirm = input(f"Delete repository {dirname} at {repo_path}? (y/n): ")
                    if confirm.lower() == 'y':
                        import shutil
                        shutil.rmtree(repo_path, ignore_errors=True)
                        print(f"Deleted repository: {dirname}")
                        found = True
                    else:
                        print(f"Skipped repository: {dirname}")
            except Exception:
                continue
    
    if not found:
        print(f"No repositories matching the criteria were found.")

def add_repo(args):
    """Add a new repository"""
    if not args.url:
        print("Error: --url is required.")
        return
    
    branch = args.branch or 'main'
    print(f"Cloning repository {args.url} (branch: {branch})...")
    
    success, repo_path, error = repo_manager.clone_repository(args.url, branch)
    
    if success:
        print(f"Successfully cloned repository to: {repo_path}")
    else:
        print(f"Failed to clone repository: {error}")

def update_repo(args):
    """Update a repository"""
    if not args.name and not args.url:
        print("Error: Either --name or --url must be specified.")
        return
    
    if not os.path.exists(repo_manager.REPO_STORAGE_BASE):
        print(f"Repository storage directory does not exist: {repo_manager.REPO_STORAGE_BASE}")
        return
    
    found = False
    
    for dirname in os.listdir(repo_manager.REPO_STORAGE_BASE):
        repo_path = os.path.join(repo_manager.REPO_STORAGE_BASE, dirname)
        
        if not os.path.isdir(repo_path) or not os.path.exists(os.path.join(repo_path, '.git')):
            continue
        
        # Check if name matches
        name_match = args.name and args.name.lower() in dirname.lower()
        
        # Check if URL matches
        url_match = False
        if args.url:
            try:
                import subprocess
                result = subprocess.run(['git', '-C', repo_path, 'config', '--get', 'remote.origin.url'], 
                                        capture_output=True, text=True)
                if result.returncode == 0 and args.url.lower() in result.stdout.strip().lower():
                    url_match = True
            except Exception:
                pass
        
        if name_match or url_match:
            print(f"Updating repository: {dirname}")
            success, error = repo_manager.update_repository(repo_path, args.branch or 'main')
            
            if success:
                print(f"Successfully updated repository at: {repo_path}")
            else:
                print(f"Failed to update repository: {error}")
            
            found = True
    
    if not found:
        print(f"No repositories matching the criteria were found.")

def main():
    parser = argparse.ArgumentParser(description='GitHub Repository Storage Manager')
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # List repositories command
    list_parser = subparsers.add_parser('list', help='List all repositories')
    list_parser.add_argument('--sort', choices=['size', 'name', 'accessed'], default='size',
                            help='Sort repositories by size, name, or last accessed time')
    list_parser.set_defaults(func=list_repos)
    
    # Clean repositories command
    clean_parser = subparsers.add_parser('clean', help='Clean up old repositories')
    clean_parser.add_argument('--days', type=int, default=30,
                             help='Maximum age in days to keep repositories that have not been accessed')
    clean_parser.add_argument('--size', type=float, default=10,
                             help='Maximum total size in GB to keep')
    clean_parser.set_defaults(func=clean_repos)
    
    # Delete repository command
    delete_parser = subparsers.add_parser('delete', help='Delete a specific repository')
    delete_parser.add_argument('--name', help='Repository directory name (partial match)')
    delete_parser.add_argument('--url', help='Repository URL (partial match)')
    delete_parser.set_defaults(func=delete_repo)
    
    # Add repository command
    add_parser = subparsers.add_parser('add', help='Add a new repository')
    add_parser.add_argument('--url', required=True, help='Repository URL')
    add_parser.add_argument('--branch', help='Branch to clone (default: main)')
    add_parser.set_defaults(func=add_repo)
    
    # Update repository command
    update_parser = subparsers.add_parser('update', help='Update a repository')
    update_parser.add_argument('--name', help='Repository directory name (partial match)')
    update_parser.add_argument('--url', help='Repository URL (partial match)')
    update_parser.add_argument('--branch', help='Branch to update (default: main)')
    update_parser.set_defaults(func=update_repo)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    args.func(args)

if __name__ == '__main__':
    main() 