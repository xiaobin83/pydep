import os
import argparse
import json
import re
import logging
import sys
import tempfile
import shutil

from git import Repo
from git import RemoteProgress
from git.cmd import Git

from dirsync import sync 

logging.basicConfig(level=logging.INFO)


pydepFilename = '.pydep-git'
pydepRepoPath = '.pydep-gitrepo'
pydepTargetInfo = '.pydep-gitinfo'


class RepoNotFoundError(Exception):
	pass

class GitProgress(RemoteProgress):
	def update(self, op_code, cur_count, max_count=None, message=''):
		sys.stdout.write(','.join([op_code, cur_count, max_count, cur_count / (max_count or 100.0), message or 'NO MESSAGE']))
		sys.stdout.write('\n')


def setupArgs():
	parser = argparse.ArgumentParser(description='setting up dependencies of project')
	parser.add_argument('--init', action='store_true')	
	parser.add_argument('--update', dest='update')
	parser.add_argument('--rev', dest='rev', default='HEAD')
	return parser.parse_args()

def getPydepIgnoreMatcher():
	return re.compile(r'^\s*\\'+pydepRepoPath+r'/\s*$')

def matchIgnore(line):
	m = getPydepIgnoreMatcher()
	return m.match(line) is not None
	

def init():
	if not os.path.exists(pydepFilename):
		pydepGit = {
			'dep name': {
				'repo': 'github.com/repo/to/clone',
				'branch': 'master',
				'rev': 'HEAD',
				'packages': [
					{
						'path': 'path/in/repo/for/checking/out',
						'target': 'target/path/for/checking/out'
					},
					{
						'path': 'another/path/in/repo/for/checking/out',
						'target': 'another/target/path/for/checking/out'
					}
				]
			}
		}
		json.dump(pydepGit, open('.pydep-git', mode='w'), indent=4)
	if not os.path.exists(pydepRepoPath):
		os.mkdir(pydepRepoPath)

	shouldAddToIgnoreList = True 
	if os.path.exists('.gitignore'):
		with open('.gitignore', mode='r') as f:
			lines = f.readlines()
			for line in lines:
				if matchIgnore(line):
					shouldAddToIgnoreList = False
					break

	if shouldAddToIgnoreList:
		with open('.gitignore', mode='a+') as f:
			f.write('\n')
			f.write('# pydep\n')
			f.write(pydepRepoPath + '/')
			f.write('\n')

def readConfig():
	with open(pydepFilename, mode='r') as f:
		return json.load(f)


def clone(url, branch, path):
	repo = Repo.clone_from(url, path, branch=branch, progress=GitProgress(), bare=True, depth=1)
	return repo

def errRepo(name, path):
	pass


def cloneIfNeeded(config, repoName, repoRev):
	clonePath = os.path.join(pydepRepoPath, repoName)
	if not os.path.exists(clonePath):
		return clone(config[repoName]['repo'], config[repoName]['branch'], clonePath)
	else:
		repo = Repo(clonePath)
		if not repo.bare:
			errRepo(repoName, clonePath)
		return repo


def checkout(repo, rev, branch, packages):
	git = Git(repo.git_dir)
	workTreePath = tempfile.mkdtemp('_pydep')
	repo.git(work_tree=workTreePath).checkout(f=True)
	return workTreePath

def sparseCheckout(repo, config, repoName):
	if not config.has_key(repoName):
		raise RepoNotFoundError()

	with repo.config_writer() as w:
		w.set('core', 'sparsecheckout', True)

	sparseConfigPath = os.path.join(repo.git_dir, 'info', 'sparse-checkout')

	c = config[repoName]
	packages = c['packages']
	sparseDirs = []
	for package in packages:
		path = package['path']
		sparseDirs.append(path + '/*\n')
	with open(sparseConfigPath, 'w+') as f:
		f.writelines(sparseDirs)
	
	return checkout(repo, config[repoName]['branch'], config[repoName]['rev'], config[repoName]['packages'])


def removeDir(path):
	shutil.rmtree(path)

def copyToTarget(tempWorkTreePath, repo, config, repoName):
	c = config[repoName]
	packages = c['packages']
	for package in packages:
		path = package['path']
		target = package['target']
		srcDir = os.path.join(tempWorkTreePath, path)
		dstDir = os.path.join(os.getcwd(), target)
		sync(srcDir, dstDir, 'sync', verbose=True, create=True)
		

def update(config, repoName, repoRev):
	if not config.has_key(repoName):
		raise RepoNotFoundError() 
	repo = cloneIfNeeded(config, repoName, repoRev)
	tempWorkTreePath = sparseCheckout(repo, config, repoName)
	copyToTarget(tempWorkTreePath, repo, config, repoName)
	removeDir(tempWorkTreePath)	


def main(args):
	if args.init:
		init()
	elif args.update is not None:
		update(readConfig(), args.update, args.rev)

if __name__ == '__main__':
	args = setupArgs()
	main(args)
