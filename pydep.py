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
class RepoRevNotFoundError(Exception):
	pass
class RepoAlreadyAddedError(Exception):
	pass

class RepoPackageTargetExistsError(Exception):
	def __init__(self, repoName, packagePath, packageTarget):
		self.repoName = repoName
		self.packagePath = packagePath
		self.packageTarget = packageTarget
	def __str__(self):
		return '"{0}" at repo "{1}" package "{2}"'.format(self.packageTarget, self.repoName, self.packagePath)

class GitProgress(RemoteProgress):
	def update(self, op_code, cur_count, max_count=None, message=''):
		sys.stdout.write(','.join([op_code, cur_count, max_count, cur_count / (max_count or 100.0), message or 'NO MESSAGE']))
		sys.stdout.write('\n')


def setupArgs():
	parser = argparse.ArgumentParser()
	parser.add_argument("command", type=str, nargs=1)
	return parser

def setupAddArgs():
	parser = argparse.ArgumentParser(prog='add')
	parser.add_argument('--name', dest='name', required=True)
	parser.add_argument('--url', dest='url', required=True)
	parser.add_argument('--branch', dest='branch', default='master')
	parser.add_argument('--rev', dest='rev', default='HEAD')
	return parser

def setupAddPackageArgs():
	parser = argparse.ArgumentParser(prog='addPackage')
	parser.add_argument('--name', dest='name', required=True)
	parser.add_argument('--path', dest='path', default='<ROOT>')
	parser.add_argument('--target', dest='target', required=True)
	return parser

def setupLockArgs():
	parser = argparse.ArgumentParser(prog='lock')
	parser.add_argument('--name', dest='name', required=True)
	return parser

def setupUpdateArgs():
	parser = argparse.ArgumentParser(prog='update')
	parser.add_argument('--name', dest='name', required=True)
	parser.add_argument('--rev', dest='rev', default=None)
	return parser

def getPydepIgnoreMatcher():
	return re.compile(r'^\s*\\'+pydepRepoPath+r'/\s*$')

def matchIgnore(line):
	m = getPydepIgnoreMatcher()
	return m.match(line) is not None

def init():
	if not os.path.exists(pydepFilename):
		pydepGit = {
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

def add(args):
	name = args.name
	url = args.url
	branch = args.branch
	rev = args.rev
	config = readConfig()
	if config.has_key(name):
		raise RepoAlreadyAddedError()
	config[name] = {
		"url": url,
		"branch": branch,
		"rev": rev,
	}
	writeConfig(config)

def checkPackages(config):
	targets = {} 
	for name, c in config.iteritems():
		if c.has_key('packages'):
			for p in c['packages']:
				path = p['path']
				target = p['target']
				if targets.has_key(target):
					info = targets[target]
					raise RepoPackageTargetExistsError(info['name'], info['path'], info['target'])
				else:
					targets[target] = {
						'name': name,
						'path': path,
						'target': target,
					}

def addPackage(args):
	name = args.name
	path = args.path
	target = args.target
	config = readConfig()
	if not config.has_key(name):
		raise RepoNotFoundError()
	packages = config[name].get('packages', [])
	packages.append({
		u'path':unicode(path),
		u'target': unicode(target)
	})
	checkPackages(config)
	config[name]['packages'] = packages
	writeConfig(config)

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
	else:
		try:
			commit = repo.iter_commits(rev=rev, max_count=1).next()
		except:
			if reentry:
				raise RepoRevNotFoundError()
			# todo: fetch specific commit, requires server support uploadpack.allowReachableSHA1InWant
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

def checkRepo(repoName, c, rev):
	print >> sys.stdout, 'checking {0} {1} {2}'.format(repoName, c['url'], rev)
	clonePath = os.path.join(pydepRepoPath, repoName)
	if not os.path.exists(clonePath):
		repo = clone(c['url'], c['branch'], clonePath)
		if rev != 'HEAD':
			ensureCommitExists(repo, c['branch'], rev)
	else:
		repo = repoFrom(clonePath)
		ensureCommitExists(repo, c['branch'], rev)
	return repo


def checkout(repo, rev, packages):
	workTreePath = tempfile.mkdtemp('_pydep')
	repo.git(work_tree=workTreePath).checkout(f=True)
	return workTreePath

def sparseCheckout(repo, c, rev):
	with repo.config_writer() as w:
		w.set('core', 'sparsecheckout', 'true')

	sparseConfigPath = os.path.join(repo.git_dir, 'info', 'sparse-checkout')

	packages = c['packages']
	sparseDirs = []
	for package in packages:
		path = package['path']
		sparseDirs.append(path + '/*\n')
	with open(sparseConfigPath, 'w') as f:
		f.writelines(sparseDirs)

	return checkout(repo, rev, c['packages'])


def removeDir(path):
	shutil.rmtree(path)

def copyToTarget(tempWorkTreePath, c):
	packages = c['packages']
	for package in packages:
		path = package['path']
		target = package['target']
		srcDir = os.path.join(tempWorkTreePath, path)
		dstDir = os.path.join(os.getcwd(), target)
		sync(srcDir, dstDir, 'sync', create=True)
		

def update(config, args):
	repoName = args.name
	c = config.get(repoName)
	if c is None:
		raise RepoNotFoundError() 
	rev = args.rev
	if rev is None:
		rev = c.get('rev', 'HEAD') 
	repo = checkRepo(repoName, c, rev)
	tempWorkTreePath = sparseCheckout(repo, c, rev)
	copyToTarget(tempWorkTreePath, c)
	removeDir(tempWorkTreePath)	

def lockRepo(repoPath):
	repo = repoFrom(repoPath)
	commit = repo.iter_commits(max_count=1).next()
	return commit.hexsha


def lock(config, args):
	repoName = args.name
	c = config.get(repoName)
	if c is None:
		raise RepoNotFoundError()
	repoPath = os.path.join(pydepRepoPath, repoName)
	rev = lockRepo(repoPath)
	c['rev'] = rev
	writeConfig(config)
	


def main(cmd, args):
	if cmd == 'init':
		init()
	elif cmd == 'update':
		p = setupUpdateArgs()
		args = p.parse_args(args)
		update(readConfig(), args)
	elif cmd == 'lock':
		p = setupLockArgs()
		args = p.parse_args(args)
		lock(readConfig(), args)
	elif cmd == 'add':
		p = setupAddArgs()
		args = p.parse_args(args)
		add(args)
	elif cmd == 'addPackage':
		p = setupAddPackageArgs()
		args = p.parse_args(args)
		addPackage(args)
	elif cmd == 'help':
		p = setupArgs()
		p.print_usage()
		print >> sys.stdout, 'Commands:'
		p = setupAddArgs()
		p.print_usage()
		p = setupAddPackageArgs()
		p.print_usage()
		p = setupUpdateArgs()
		p.print_usage()
		p = setupLockArgs()
		p.print_usage()

if __name__ == '__main__':
	p = setupArgs()
	cmd = p.parse_args(sys.argv[1:2])
	main(cmd.command[0], sys.argv[2:])
	
