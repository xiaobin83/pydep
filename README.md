# pydep

A shortcut for git sparse-checkout, for managing dependencies to part of git repo.

If your project dep to a complete git repo, it's better to use git-submodule. (even pydep can handle this)

If your project is go project, use [golang/dep](https://github.com/golang/dep) instead.


> pydep<span></span>.py help

	usage: pydep.py [-h] command
	Commands:
	usage: add [-h] --name NAME --url URL [--branch BRANCH] [--rev REV]
	usage: addPackage [-h] --name NAME [--path PATH] --target TARGET
	usage: update [-h] [--name NAME] [--rev REV]
	usage: lock [-h] [--name NAME]

1. Init pydep repo

	> pydep<span></span>.py init

2. Add dependence repo

	> pydep<span></span>.py add --name "ShaderForge" --url "https://github.com/xiaobin83/ShaderForge.git

3. Add package from this repo

	> pydep<span></span>.py addPackage --name ShaderForge --path "Shader Forge/Assets/ShaderForge" --target Tools/ShaderForge

4. Checkout dependence

	> pydep<span></span>.py update --name ShaderForge

5. Lock commit of dependence

	> pydep<span></span>.py lock --name ShaderForge

And now, you will find .pydep-gitrepo folder and .pydep-git file inside your poject.

> .pydep-git

	{
		"ShaderForge": {
			"url": "https://github.com/xiaobin83/ShaderForge.git", 
			"packages": [
				{
					"path": "Shader Forge/Assets/ShaderForge", 
					"target": "Tools/ShaderForge"
				}
			], 
			"rev": "94888056db0de477c62eec98eabd5fc18d073ec6", 
			"branch": "master"
		}
	}

You can add multiple packages in "packages" array.

If you want to update a locked ( rev point to a specific commit ) repo to HEAD or other commit, you can use,

> pydep<span></span>.py update --name ShaderForge --rev HEAD

it will update Tools/ShaderForge to specific commit, but will remain .pydep-git unchanged. To lock it, you can use, 

> pydep<span></span>.py lock --name ShaderForge

again.


If you want to dep to a complete repo (not recommanded), at step 3 adding package, you can use, (assuming repo ios-cmake already added)

> pydep<span></span>.py addPackage --name ios-cmake --target Tools/ios-cmake

And now you will have

	{
	    "ios-cmake": {
	        "url": "https://github.com/xiaobin83/ios-cmake.git", 
	        "packages": [
	            {
	                "path": "<ROOT>", 
	                "target": "Tools/ios-cmake"
	            }
	        ], 
	        "rev": "HEAD", 
	        "branch": "master"
	    }
	}

in .pydep-git file. Notice "path" point to "<ROOT>". And a repo only can have one <ROOT> package without other packages.

You also can edit .pydep-git manually.

Command *update* and *lock* without --name will apply to all repo.

Exceptions,

* RepoNotFoundError, --name takes repo name not inside .pydep-git

* RepoIsNotBareError, already have --name \<NAME\> in .pydep-gitrepo/\<NAME\>, but it's not bare repo. just delete it manually from .pydep-gitrepo dir then update.

* RepoInvalidError, already have --name \<NAME\> in .pydep-gitrepo/\<NAME\>, but it's not a git repo. Just delete it manually from .pydep-gitrepo dir then update.

* RepoRevNotFoundError, specific commit --rev \<REV\> not belong to repo.

* RepoAlreadyAddedError, adding --name \<NAME\> already exists in .pydep-git

* RepoPackageTargetExistsError, more than one package (all the repo) has the same checkout target.







