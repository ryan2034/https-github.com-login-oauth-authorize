# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module builders for bbuildbot."""

from __future__ import print_function

import contextlib
import os
import re
import subprocess
import tempfile
import time

from chromite.cbuildbot import repository
from chromite.cbuildbot.builders import generic_builders
from chromite.cbuildbot.stages import generic_stages
from chromite.cbuildbot.stages import sync_stages
from chromite.lib import cros_build_lib
from chromite.lib import cros_logging as logging
from chromite.lib import osutils


class EmulatorFailedToStart(Exception):
  """The emulator process isn't running after 10 seconds."""


class EmulatorNotReady(Exception):
  """The adb devices command did not discover a valid emulator serial number."""


class BrilloStageBase(generic_stages.BuilderStage):
  """Base class for all symbols build stages."""

  def BrilloRoot(self):
    """Root for repo checkout of Brillo."""
    # Turn /mnt/data/b/cbuild/android -> /mnt/data/b/cbuild/android_brillo

    # We have to be OUTSIDE the build root, since this is a new repo checkout.
    # We don't want to be in /tmp both because we might not fit, and because the
    # initial sync is expensive enough that we don't want to have to redo it if
    # avoidable.
    return self._run.buildroot + '_brillo'

  def BuildOutput(self):
    """Returns directory for brillo build output."""
    return os.path.join(self.BrilloRoot(), 'out')

  def FindShellCmd(self, cmd):
    target = self._run.config.lunch_target

    cmd_list = []
    cmd_list.append('. build/envsetup.sh')
    cmd_list.append('lunch %s' % target)
    cmd_list.append('OUT_DIR=%s' % self.BuildOutput())
    cmd_list.append(' '.join(cmd))

    return ' > /dev/null && '.join(cmd_list)

  def RunLunchCommand(self, cmd, **kwargs):
    """RunCommand with lunch setup."""
    # Default directory to run in.
    kwargs.setdefault('cwd', self.BrilloRoot())

    # We use a shell invocation so environmental variables are preserved.
    cmd = self.FindShellCmd(cmd)
    return cros_build_lib.RunCommand(cmd, shell=True, **kwargs)


class BrilloCleanStage(BrilloStageBase):
  """Compile the Brillo checkout."""

  def PerformStage(self):
    """Clean up Brillo build output."""
    osutils.RmDir(self.BuildOutput(), ignore_missing=True)

    if self._run.options.clobber:
      osutils.RmDir(self.BrilloRoot(), ignore_missing=True)


class BrilloSyncStage(BrilloStageBase):
  """Sync Brillo code to a sub-directory."""

  def PerformStage(self):
    """Fetch and/or update the brillo source code."""
    osutils.SafeMakedirs(self.BrilloRoot())
    brillo_repo = repository.RepoRepository(
        manifest_repo_url=self._run.config.brillo_manifest_url,
        branch=self._run.config.brillo_manifest_branch,
        directory=self.BrilloRoot())
    brillo_repo.Initialize()
    brillo_repo.Sync()


class BrilloBuildStage(BrilloStageBase):
  """Compile the Brillo checkout."""

  def PerformStage(self):
    """Do the build work."""
    self.RunLunchCommand(['make', '-j', '32'])


class BrilloVmTestStage(BrilloStageBase):
  """Compile the Brillo checkout."""

  @contextlib.contextmanager
  def RunEmulator(self):
    """Run an emulator process in the background, kill it on exit."""
    with tempfile.NamedTemporaryFile(prefix='emulator') as logfile:
      cmd = self.FindShellCmd([self._run.config.emulator])
      logging.info('Starting emulator: %s', cmd)
      p = subprocess.Popen(
          args=(cmd,),
          shell=True,
          close_fds=True,
          stdout=logfile,
          stderr=subprocess.STDOUT,
          cwd=self.BrilloRoot(),
          )


      try:
        # Give the emulator a little time, and make sure it's still running.
        # Failure could be an crash, another copy was left running, etc.
        time.sleep(10)
        if p.poll() is not None:
          logging.error('Emulator is not running after 10 seconds, aborting.')
          raise EmulatorFailedToStart()

        yield
      finally:
        if p.poll() is None:
          # Kill emulator, if it's still running.
          logging.info('Stopping emulator.')
          p.terminate()

        p.wait()

        # Read/dump the emulator output.
        logging.info('*')
        logging.info('* Emulator Output')
        logging.info('*\n%s', osutils.ReadFile(logfile.name))
        logging.info('*')
        logging.info('* Emulator End')
        logging.info('*')

  def DiscoverEmulatorSerial(self):
    """Query for the serial number of the emulator.

    Returns:
      String containing the serial number of the emulator, or None
    """
    result = self.RunLunchCommand(
        ['adb', 'devices'],
        redirect_stdout=True,
        combine_stdout_stderr=True)

    # Command output before we are ready:
    #   List of devices attached
    #   emulator-5554 offline

    # Command output after we are ready:
    #   List of devices attached
    #   emulator-5554 device

    m = re.search(r'^([\w-]+)\tdevice$', result.output, re.MULTILINE)
    if m:
      return m.group(1)
    return None

  def WaitForEmulatorSerial(self):
    """Retry the query for the emulator serial number, until it's ready.

    Returns:
      String containing the serial number of the emulator.

    Raises:
      EmulatorNotReady if we timeout waiting (after several minutes).
    """
    for _ in xrange(20):
      result = self.DiscoverEmulatorSerial()
      if result:
        return result
      time.sleep(10)

    raise EmulatorNotReady()

  def PerformStage(self):
    """Run the VM Tests."""
    with self.RunEmulator():
      # To see the emulator, we must sometimes kill/restart the adb server.
      self.RunLunchCommand(['adb', 'kill-server'])

      # Wait for the emulator to come up enough to give us a serial number.
      serial = self.WaitForEmulatorSerial()

      # Run the tests.
      logging.info('Running tests against %s', serial)
      self.RunLunchCommand(
          ['external/autotest/site_utils/test_droid.py',
           '--debug', serial, 'brillo_WhitelistedGtests'],
          cwd=self.BrilloRoot())


class BrilloBuilder(generic_builders.Builder):
  """Builder that performs sync, then exits."""

  def GetSyncInstance(self):
    """Returns an instance of a SyncStage that should be run."""
    return self._GetStageInstance(sync_stages.SyncStage)

  def RunStages(self):
    """Run something after sync/reexec."""
    self._RunStage(BrilloCleanStage)
    self._RunStage(BrilloSyncStage)
    self._RunStage(BrilloBuildStage)
    self._RunStage(BrilloVmTestStage)
