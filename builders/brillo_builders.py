# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module builders for bbuildbot."""

from __future__ import print_function

import os

from chromite.lib import cros_build_lib
from chromite.lib import osutils

from chromite.cbuildbot.builders import generic_builders
from chromite.cbuildbot.stages import generic_stages
from chromite.cbuildbot.stages import sync_stages
from chromite.cbuildbot import repository


class BrilloStageBase(generic_stages.BuilderStage):
  """Base class for all symbols build stages."""

  def BrilloRoot(self):
    # Turn /mnt/data/b/cbuild/android -> /mnt/data/b/cbuild/android_brillo

    # We have to be OUTSIDE the build root, since this is a new repo checkout.
    # We don't want to be in /tmp both because we might not fit, and because the
    # initial sync is expensive enough that we don't want to have to redo it if
    # avoidable.
    return self._run.buildroot + '_brillo'

  def BuildOutput(self):
    # We store brillo build output in brillo's default output directory.
    #  (ex: brillo_root/out)
    return os.path.join(self.BrilloRoot(), 'out')


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
    """Do the sync work."""
    osutils.SafeMakedirs(self.BrilloRoot())

    # Fetch and/or update the brillo source code.
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
    cmd_list = []
    cmd_list.append('. build/envsetup.sh')
    cmd_list.append('lunch brilloemulator_arm-eng')
    cmd_list.append('OUT_DIR=%s' % self.BuildOutput())
    cmd_list.append('make -j 32')

    # We use a shell invocation so environmental variables are preserved.
    cmd = ' && '.join(cmd_list)
    cros_build_lib.RunCommand(cmd, shell=True, cwd=self.BrilloRoot())


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
