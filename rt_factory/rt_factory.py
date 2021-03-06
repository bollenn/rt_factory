# -*- coding: utf-8 -*-
import requests
from requests.auth import HTTPBasicAuth
import os
try:
    from urllib import urlencode
except ImportError:
    from urllib.parse import urlencode
import logging

# get the artifactory url from the environment
ARTIFACTORY_URL = os.environ.get('ARTIFACTORY_URL',
                                 'http://localhost:8080/artifactory/api/')
ARTIFACTORY_API_KEY = os.environ.get('ARTIFACTORY_API_KEY', '')


class ApiError(Exception):
    pass

class ArtifactoryApi:

    def __init__(self, url = ARTIFACTORY_URL):
        self.url = url
        self.api_key_header = None

    def _get_from_url(self, full_url):
        resp = requests.get(full_url, headers=self.api_key_header)
        if not resp.ok:
            # This means something went wrong.
            raise ApiError('GET {} {}'.format(full_url, resp.status_code))
        return resp.json()

    def _get(self, path):
        return self._get_from_url(self.url + path)

    def _post(self, path, payload):
        resp = requests.post(self.url + path, json = payload, headers=self.api_key_header)
        if not resp.ok:
            # This means something went wrong.
            raise ApiError('POST {} {} {}'.format(path, resp.status_code, resp.content))
        return resp

    def _put(self, path, payload=None):
        resp = requests.put(self.url + path, json = payload, headers=self.api_key_header)
        if not resp.ok:
            # This means something went wrong.
            raise ApiError('PUT {} {} {}'.format(path, resp.status_code, resp.content))
        return resp

    def _put_file(self, path, filename, **kwargs):
        with open(filename, "rb") as file:
            resp = requests.put(self.url + path, data = file, **kwargs)
            if not resp.ok:
                # This means something went wrong.
                raise ApiError('PUT {} {} {}'.format(path, resp.status_code, resp.content))
        return resp

    def get_repository(self, name):
        return self._get(name).json()

    def create_repository(self, name, configuration):
        for repo in self._get('repositories'):
            if repo['key'] == name:
                print('Warning: repository {} already exists. Ignoring creating it to avoid dataloss.'.format(name))
                return

        path = 'repositories/{}'.format(name)
        return self._put(path, configuration)

    def update_repository(self, name, data):
        # make sure the repo exists
        self.create_repository(name, data)

        path = 'repositories/{}'.format(name)
        return self._post(path, data)


    def create_or_replace_user(self, name, password, groups = ['developers', 'readers']):
        path = 'security/users/{}'.format(name)
        self._put(path, {'email': '{}@melexis.com'.format(name),
                         'password': password,
                         'groups': groups,
                         })

    def create_group(self, name, description = ''):
        path = 'security/groups/{}'.format(name)
        try:
            group = self._get(path)
        except:
            group ={}

        group['name'] = name
        group['description'] = description
        self._put(path,group)

    def create_user(self, name):
        path = 'security/users/{}'.format(name)
        try:
            user = self._get(path)
            print("User {} already exists".format(name))
            return user
        except:
            user ={}

        user['name'] = name
        user['email'] = name + "@melexis.com"
        user['password'] = 'password'
        user['groups'] = ['users', 'readers']
        self._put(path,user)


    def add_user_to_group(self, user, group):
        path = 'security/users/{}'.format(user)
        user = self._get(path)
        if group not in user['groups'] or []:
            user['groups'].append(group)
        self._post(path, user)

    def get_permission(self, target_name):
        path = 'security/permissions/{}'.format(target_name)
        current = self._get(path)
        return current

    def add_group_to_permission(self, target_name, group_name, access = ["r", "n"] ):
        path = 'security/permissions/{}'.format(target_name)
        current = self.get_permission(target_name)

        print(current)
        groups = current['principals'].get('groups', {})
        groups[group_name] = access
        current['principals']['groups'] = groups
        self._put(path,current)

    def add_repository_to_permission(self, target_name, repo ):
        path = 'security/permissions/{}'.format(target_name)
        current = self.get_permission(target_name)

        repos = current['repositories']
        if repo not in repos:
            repos.append(repo)
        current['repositories'] = repos
        self._put(path,current)

    def create_permission(self, target_name, includes = "**", excludes = ""):
        path = 'security/permissions/{}'.format(target_name)
        try:
            current = self.get_permission()
        except:
            current = {}

        current['name'] = target_name;
        current['includesPattern'] = includes;
        current['excludesPattern'] = excludes;
        current['repositories'] = current.get('repositories', [])
        current['principals'] = current.get('principals', {'users': {}, 'groups': {}})
        self._put(path, current)

    def add_public_key(self, filename):
        path = 'gpg/key/public'
        self._put_file(path, filename)

    def add_private_key(self, filename, phrase):
        path = 'gpg/key/private'
        self._put_file(path, filename, headers={'X-GPG-PASSPHRASE': phrase})

    def get_link_to_last_modified(self, repository, path):
        """ Searches for artifacts with the latest modification date.

        Args:
            repo (str): The repository name.
            path (str): The full path to the file to be searched for.

        Returns:
            str: Download url to the artifact.
        """
        path = 'storage/{repo}/{path}/?lastModified'.format(repo=repository, path=path)
        temp_link = self._get(path)['uri']
        return self._get_from_url(temp_link)['downloadUri']

    def get_link_to_last_version(self, repository, path):
        """ Searches for artifacts with the latest value in the "version" property. Only artifacts
        with a "version" property expressly defined in lower case will be taken into account. 

        Args:
            repository (str): The repository name.
            path (str): The full path to the file to be searched for.

        Returns:
            str: Download url to the artifact.

        Notes:
            Requires an authenticated user (not anonymous).
        """
        path = 'versions/{repo}/{path}?listFiles=1'.format(repo=repository, path=path)
        temp_link = self._get(path)
        return temp_link['artifacts'][0]['downloadUri']

    def download_file(self, url, path_to_file):
        """ Download a file from the Artifactory server.

        Args:
            url (str): Url to the file to be downloaded.
            path_to_file (str): Path + filename to be used for downloading the file.
        """
        dl_content = requests.get(url, stream=True)
        with open(path_to_file, 'wb') as output_file:
            for chunk in dl_content.iter_content(chunk_size=1024): 
                if chunk:
                    output_file.write(chunk)

    def set_authentication_api_key(self, api_key=ARTIFACTORY_API_KEY):
        """ Set the API Key for running commands needing authentication.

        Args:
            the_key (str): The users Artifactory API key.
        """
        self.api_key_header = {'X-JFrog-Art-Api':api_key}

    def add_properties(self, repository, path, properties):
        """ Set properties of an artifact

        Args:
            repository (str): The repository name.
            path (str): The full path to the file to be searched for.
            properties (list): Json list of properties to set on the artifact.
        """
        prop = urlencode(properties).replace('&', '|')
        path = 'storage/{repo}/{path}?properties={prop}&recursive=1'.format(repo=repository, path=path, prop=prop)
        self._put(path, properties)
