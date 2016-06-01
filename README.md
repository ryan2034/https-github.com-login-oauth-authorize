This repository exists to configure cbuildbot based bruteus builds.

To check this out as a repo checkout:

```sh
repo init -u https://android.googlesource.com/platform/bbuildbot_config
```

To perform a local build:

```sh
bin/cbuildbot --buildroot ~/tmp/test_buildroot \
  --buildbot --debug --config_repo  \
  https://android.googlesource.com/platform/bbuildbot_config \
  bbuildbot
```

To perform a test build with local changes:

```sh
bin/cbuildbot --nobootstrap --noreexec \
  --buildroot ~/tmp/test_buildroot \
  --buildbot --debug --config_repo  \
  https://android.googlesource.com/platform/bbuildbot_config \
  bbuildbot
```
