#!/usr/bin/env python

import argparse
import os
from datetime import datetime

import yaml
from github import Auth, Github


def pause(env, service, repo, branch):
    """Pause Continuous Delivery (C/D) of the service in the target environment."""

    file_path = f'environments/{env}/{service}/application.yaml'
    
    contents = repo.get_contents(file_path, ref=repo.default_branch)
    
    app = yaml.safe_load(contents.decoded_content.decode())
    
    key = f'argocd-image-updater.argoproj.io/{service}.ignore-tags'
    
    app['metadata']['annotations'][key] = '*'
    
    app_yaml = yaml.dump(app, default_flow_style=False, explicit_start=True)
    
    repo.update_file(contents.path, f'Pause {service} in {env}.', app_yaml, contents.sha, branch=branch)
    
    print(f'Updated the "{file_path}" file in the "{branch}" branch of the "{repo.name}" remote repository')


def resume(env, service, repo, branch):
    """Resume Continuous Delivery (CD) of the service in the target environment."""

    file_path = f'environments/{env}/{service}/application.yaml'
    
    contents = repo.get_contents(file_path, ref=repo.default_branch)
    
    app = yaml.safe_load(contents.decoded_content.decode())
    
    key = f'argocd-image-updater.argoproj.io/{service}.ignore-tags'
    
    app['metadata']['annotations'].pop(key, None)
    
    app_yaml = yaml.dump(app, default_flow_style=False, explicit_start=True)

    repo.update_file(contents.path, f'Resume {service} in {env}.', app_yaml, contents.sha, branch=branch)

    print(f'Updated the "{file_path}" file in the "{branch}" branch of the "{repo.name}" remote repository')


def get_versions(charts_dir, env, repo):
    """Get the latest deployed versions of the services."""

    versions = {}

    services = repo.get_contents(charts_dir)

    for service in services:
        
        file_path = f'{service.path}/.argocd-source-{service.name}-{env}.yaml'

        contents = repo.get_contents(file_path, ref=repo.default_branch)

        params = yaml.safe_load(contents.decoded_content.decode())

        for param in params['helm']['parameters']:
            if param['name'] == 'image.tag':
                versions[service.name] = param['value']

    return versions


def options():
    """Add command-line arguments to the script."""

    parser = argparse.ArgumentParser()

    parser.add_argument('--source-env', help='Select environment')

    parser.add_argument('--target-env', help='Select environment')

    parser.add_argument('--action', help='Select an action to perform')

    return parser.parse_args()


def update_versions(env, versions, repo, branch):
    """Update the service versions to the latest ones deployed in the specified environment."""

    target_dir = f'environments/{env}'

    services = repo.get_contents(target_dir)

    for service in services:

        file_path = f'{service.path}/application.yaml'

        contents = repo.get_contents(file_path, ref=repo.default_branch)

        app = yaml.safe_load(contents.decoded_content.decode())

        new_params = []

        for param in app['spec']['source']['helm']['parameters']:
            if param['name'] != 'image.tag':
                new_params.append(param)

        image_tag = {'name': 'image.tag', 'value': versions[service.name]}
        new_params.append(image_tag)

        app['spec']['source']['helm']['parameters'] = new_params

        app_yaml = yaml.dump(app, default_flow_style=False, explicit_start=True)

        repo.update_file(contents.path, f'Updated {service.name} in {env}.', app_yaml, contents.sha, branch=branch)

        print(f'Updated the "{file_path}" file in the "{branch}" branch of the "{repo.name}" remote repository')


def create_branch(repo, branch):
    """Create a new branch in the remote GitHub repository."""

    sb = repo.get_branch(repo.default_branch)

    repo.create_git_ref(ref='refs/heads/' + branch, sha=sb.commit.sha)

    print(f'Created a "{branch}" branch in the "{repo.name}" remote repository')


def create_pr(repo, branch, title):
    """Create a Pull Request in the remote GitHub repository."""

    base = repo.default_branch

    repo.create_pull(base=base, head=branch, title=title)

    print(f'Created a pull request in the "{repo.name}" remote repository')


def get_repo(name):
    """Get GitHub repository by name"""

    github_token = os.environ['GITHUB_TOKEN']

    auth = Auth.Token(github_token)

    g = Github(auth=auth)

    return g.get_repo(name)


def main():
    """Entrypoint to the GitOps script."""

    repository = get_repo('antonputra/k8s')

    args = options()

    today = datetime.today().strftime('%Y-%m-%d')

    env_dir = f'environments/{args.target_env}'

    if args.action == 'pause':

        new_branch = f'pause-{args.target_env}-{today}'

        create_branch(repository, new_branch)

        services = repository.get_contents(env_dir)

        for svc in services:
            pause(args.target_env, svc.name, repository, new_branch)

        create_pr(repository, new_branch, f'Freeze the {args.target_env} environment.')

    if args.action == 'resume':

        new_branch = f'resume-{args.target_env}-{today}'

        create_branch(repository, new_branch)

        services = repository.get_contents(env_dir)
        
        for svc in services:
            resume(args.target_env, svc.name, repository, new_branch)

        create_pr(repository, new_branch, f'Unfreeze the {args.target_env} environment.')

    # Prepare the production push with the latest deployed versions from the dev environment
    if args.action == 'push':

        new_branch = f'prod-push-{today}'

        create_branch(repository, new_branch)

        latest_versions = get_versions('helm-charts', args.source_env, repository)

        update_versions(args.target_env, latest_versions, repository, new_branch)


        create_pr(repository, new_branch, f'Production Push.')


if __name__ == "__main__":
    main()