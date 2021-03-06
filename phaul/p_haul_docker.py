#
# Docker container hauler
#

import os
import logging
import time
import signal
import fs_haul_subtree
import json
import subprocess as sp
from subprocess import PIPE

# TODO use docker-py
# import docker


# Some constants for docker
docker_bin = "/usr/bin/docker-1.9.0-dev"
docker_dir = "/var/lib/docker/"
docker_run_meta_dir = "/var/run/docker/execdriver/native"


class p_haul_type:
	def __init__(self, ctid):

		# TODO ctid must > 3 digit; with docker-py, we can also resolve
		#  container name
		if len(ctid) < 3:
			raise Exception("Docker container ID must be > 3 digits")

		self._ctid = ctid
		self._ct_rootfs = ""

	def init_src(self):
		self.full_ctid = self.get_full_ctid()
		self.__load_ct_config(docker_dir)

	def init_dst(self):
		pass

	def adjust_criu_req(self, req):
		"""Add module-specific options to criu request"""
		pass

	def root_task_pid(self):
		# Do we need this for Docker?
		return self.full_ctid

	def __load_ct_config(self, path):

		# Each docker container has 3 directories that need to be
		# migrated: (1) root filesystem, (2) container configuration,
		# (3) runtime meta state
		self._ct_rootfs = os.path.join(docker_dir, "aufs/mnt", self.full_ctid)
		self._ct_config_dir = os.path.join(docker_dir, "containers", self.full_ctid)
		self._ct_run_meta_dir = os.path.join(docker_run_meta_dir, self.full_ctid)
		logging.info("Container rootfs: %s", self._ct_rootfs)
		logging.info("Container config: %s", self._ct_config_dir)
		logging.info("Container meta: %s", self._ct_run_meta_dir)

	def set_options(self, opts):
		pass

	# Remove any specific FS setup
	def umount(self):
		pass

	def get_fs(self, fs_sk=None):
		# use rsync for rootfs and configuration directories
		return fs_haul_subtree.p_haul_fs([self._ct_rootfs, self._ct_config_dir])

	def get_fs_receiver(self, fs_sk=None):
		return None

	def get_full_ctid(self):
		dir_name_list = os.listdir(os.path.join(docker_dir, "containers"))

		full_id = ""
		for name in dir_name_list:
			name = name.rsplit("/")
			if (name[0].find(self._ctid) == 0):
				full_id = name[0]
				break

		if full_id != "":
			return full_id
		else:
			raise Exception("Can not find container fs")

	def final_dump(self, pid, img, ccon, fs):
		logging.info("Dump docker container %s", pid)

		# TODO: docker API does not have checkpoint right now
		# cli.checkpoint() so we have to use the command line
		# cli = docker.Client(base_url='unix://var/run/docker.sock')
		# output = cli.info()
		# call docker API

		logf = open("/tmp/docker_checkpoint.log", "w+")
		image_path_opt = "--image-dir=" + img.image_dir()
		ret = sp.call([docker_bin, "checkpoint", image_path_opt, self._ctid],
			stdout = logf, stderr = logf)
		if ret != 0:
			raise Exception("docker checkpoint failed")

	#
	# Meta-images for docker -- /var/run/docker
	#
	def get_meta_images(self, path):
		# Send the meta state file with criu images
		return [(os.path.join(self._ct_run_meta_dir, "state.json"), "state.json"),
		(os.path.join(path, "descriptors.json"), "descriptors.json")]

	def put_meta_images(self, dir):
		# Create docker runtime meta dir on dst side
		with open(os.path.join(dir, "state.json")) as data_file:
			data = json.load(data_file)
		self.full_ctid = data["id"]

		self.__load_ct_config(docker_dir)
		os.makedirs(self._ct_run_meta_dir)
		pd = sp.Popen(["cp", os.path.join(dir, "state.json"), self._ct_run_meta_dir], stdout = PIPE)
		pd.wait()

	def kill_last_docker_daemon(self):
		p = sp.Popen(['pgrep', '-l', docker_bin], stdout=sp.PIPE)
		out, err = p.communicate()

		for line in out.splitlines():
			line = bytes.decode(line)
			pid = int(line.split(None, 1)[0])
			os.kill(pid, signal.SIGKILL)

	def final_restore(self, img, criu):
		logf = open("/tmp/docker_restore.log", "w+")

		# Kill any previous docker daemon in order to reload the
		# status of the migrated container
		self.kill_last_docker_daemon()

		# start docker daemon in background
		sp.Popen([docker_bin, "daemon", "-s", "aufs"],
			stdout = logf, stderr = logf)
		# daemon.wait() TODO: docker daemon not return
		time.sleep(2)

		image_path_opt = "--image-dir=" + img.image_dir()
		ret = sp.call([docker_bin, "restore", image_path_opt, self._ctid],
						stdout = logf, stderr = logf)
		if ret != 0:
			raise Exception("docker restore failed")

	def can_pre_dump(self):
		# XXX: Do not do predump for docker right now. Add page-server
		# to docker C/R API, then we can enable the pre-dump
		return False

	def dump_need_ps(self):
		return False
