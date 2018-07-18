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

pydepFilename = '.pydep-git'
pydepRepoPath = '.pydep-gitrepo'
pydepTargetInfo = '.pydep-gitinfo'


class RepoNotFoundError(Exception):
	def __init__(self, repoName):
		pass
class RepoIsNotBareError(Exception):
	def __init__(self, repoName):
		pass
class RepoInvalidError(Exception):
	def __init__(self, repoName, innerException):
		pass
class RepoRevNotFound(Exception):
	pass

class GitProgress(RemoteProgress):
	def update(self, op_code, cur_count, max_count=None, message=''):
		sys.stdout.write(','.join([op_code, cur_count, max_count, cur_count / (max_count or 100.0), message or 'NO MESSAGE']))
		sys.stdout.write('\n')


def setupArgs():
	parser = argparse.ArgumentParser(description='setting up dependencies of project')
	parser.add_argument('--init', action='store_true')	
	parser.add_argument('--update', dest='update')
	parser.add_argument('--lock', dest='lock')
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
		json.dump(pydepGit, open(pydepFilename, mode='w'), indent=4)
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
def writeConfig(config):
	json.dump(config, open(pydepFilename, mode='w'), indent=4)

def clone(url, branch, path):
	print >> sys.stdout, 'cloning ' + url + ' ' + branch
	repo = Repo.clone_from(url, path, branch=branch, bare=True, depth=1)
	return repo

def ensureCommitExists(repo, branch, rev, reentry=False):
	if rev == 'HEAD':
		print >> sys.stdout, 'rev at HEAD, fetching from remote branch ' + branch
		repo.remotes.origin.fetch(branch, depth=1)
	try:
		commit = repo.iter_commits(rev=rev, max_count=1).next()
	except:
		if reentry:
			raise RepoRevNotFound()
		print >> sys.stdout, 'commit ' + rev + ' not exists, try fetch all commits'
		repo.remotes.origin.fetch(branch, unshallow=True)
		ensureCommitExists(repo, branch, rev, True)	

def repoFrom(repoPath):
	try:
		repo = Repo(repoPath)
	except Exception, e:
		raise RepoInvalidError(repoName, e) 
	if not repo.bare:
		raise RepoIsNotBareError(repoName)
	return repo

def cloneIfNeeded(config, repoName):
	clonePath = os.path.join(pydepRepoPath, repoName)
	c = config[repoName]
	rev = c.get('rev', 'HEAD')
	if not os.path.exists(clonePath):
		repo = clone(c['repo'], c['branch'], clonePath)
		if rev != 'HEAD':
			ensureCommitExists(repo, c['branch'], rev)
	else:
		repo = repoFrom(clonePath)
		ensureCommitExists(repo, c['branch'], rev)
	return repo


def checkout(repo, rev, branch, packages):
	workTreePath = tempfile.mkdtemp('_pydep')
	repo.git(work_tree=workTreePath).checkout(f=True)
	return workTreePath

def sparseCheckout(repo, config, repoName):
	if not config.has_key(repoName):
		raise RepoNotFoundError()

	with repo.config_writer() as w:
		w.set('core', 'sparsecheckout', 'true')

	sparseConfigPath = os.path.join(repo.git_dir, 'info', 'sparse-checkout')

	c = config[repoName]
	packages = c['packages']
	sparseDirs = []
	for package in packages:
		path = package['path']
		sparseDirs.append(path + '/*\n')
	with open(sparseConfigPath, 'w') as f:
		f.writelines(sparseDirs)

	if c.has_key('rev'):
		rev = c['rev']
	else:
		rev = 'HEAD'
	
	return checkout(repo, c['branch'], rev, c['packages'])


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
		sync(srcDir, dstDir, 'sync', create=True)
		

def update(config, repoName):
	if not config.has_key(repoName):
		raise RepoNotFoundError() 
	repo = cloneIfNeeded(config, repoName)
	tempWorkTreePath = sparseCheckout(repo, config, repoName)
	copyToTarget(tempWorkTreePath, repo, config, repoName)
	removeDir(tempWorkTreePath)	

def lockRepo(repoPath):
	repo = repoFrom(repoPath)
	commit = repo.iter_commits(max_count=1).next()
	return commit.hexsha


def lock(config, repoName):
	if not config.has_key(repoName):
		raise RepoNotFoundError(repoName)
	c = config[repoName]

	rev = c.get('rev', 'HEAD')
	if rev == 'HEAD':
		repoPath = os.path.join(pydepRepoPath, repoName)
		rev = lockRepo(repoPath)
		c['rev'] = rev
		writeConfig(config)
	

def main(args):
	if args.init:
		init()
	elif args.update is not None:
		update(readConfig(), args.update)
	elif args.lock:
		lock(readConfig(), args.lock)

if __name__ == '__main__':
	args = setupArgs()
	main(args)
