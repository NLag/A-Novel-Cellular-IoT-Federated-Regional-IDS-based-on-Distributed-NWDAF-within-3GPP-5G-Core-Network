<table style="border-collapse: collapse; border: none;">
  <tr style="border-collapse: collapse; border: none;">
    <td style="border-collapse: collapse; border: none;">
      <a href="http://www.openairinterface.org/">
         <img src="./images/oai_final_logo.png" alt="" border=3 height=50 width=150>
         </img>
      </a>
    </td>
    <td style="border-collapse: collapse; border: none; vertical-align: center;">
      <b><font size = "5">OpenAirInterface 5G Core Network Deployment : Pulling Container Images</font></b>
    </td>
  </tr>
</table>

# This page is only valid for a `Ubuntu` host.

If you are using any other distributions, please refer to [Build your own images](./BUILD_IMAGES.md).

If you want to use a specific branch or commit, please refer to [Build your own images](./BUILD_IMAGES.md).

# Pulling the images from Docker Hub #

The images are hosted under the oai account `oaisoftwarealliance`.

**All images that are currently pushed to Docker-Hub have an `Ubuntu-22.04` base image.**

Once again you may need to log on [docker-hub](https://hub.docker.com/) if your organization has the reached pulling limit as `anonymous`.

```bash
$ docker login
Login with your Docker ID to push and pull images from Docker Hub. If you don't have a Docker ID, head over to https://hub.docker.com to create one.
Username:
Password:
```

The OAI CI/CD team has automated more frequent pushes to Docker-Hub on `oaisoftwarealliance` account. Two important things to be noted:
  - We are making pushes on the `develop` tag whenever a contribution has been accepted. These images are **EXPERIMENTAL**.
  - Release tag `vx.x.x` contains the release code
  - Images are published for ARM v9 and x86 architecture

Now pull images according to your requirement,

```bash
#!/bin/bash
docker pull oaisoftwarealliance/oai-amf:v2.2.0
docker pull oaisoftwarealliance/oai-nrf:v2.2.0
docker pull oaisoftwarealliance/oai-upf:v2.2.0
docker pull oaisoftwarealliance/oai-smf:v2.2.0
docker pull oaisoftwarealliance/oai-udr:v2.2.0
docker pull oaisoftwarealliance/oai-udm:v2.2.0
docker pull oaisoftwarealliance/oai-ausf:v2.2.0
docker pull oaisoftwarealliance/oai-upf-vpp:v2.1.0
docker pull oaisoftwarealliance/oai-nssf:v2.2.0
docker pull oaisoftwarealliance/oai-pcf:v2.2.0
docker pull oaisoftwarealliance/oai-lmf:v2.2.0
# Utility image to generate traffic
docker pull oaisoftwarealliance/trf-gen-cn5g:latest
```

Finally you may logoff --> your token is stored in plain text..

```bash
$ docker logout
```

We will push new versions when new features are validated.

# Synchronizing the tutorials #

**CAUTION: PLEASE READ THIS SECTION VERY CAREFULLY!**

This repository only has tutorials and Continuous Integration scripts.

```bash
# Clone directly on the latest release tag
git clone https://gitlab.eurecom.fr/oai/cn5g/oai-cn5g-fed.git
cd oai-cn5g-fed
# If you forgot to clone directly to the latest release tag
git checkout -f v2.2.0

# Synchronize all git submodules
./scripts/syncComponents.sh
---------------------------------------------------------
Detected branch of fed repository : master
OAI-PCF      component branch : master
OAI-NRF      component branch : master
OAI-SMF      component branch : master
OAI-UPF      component branch : master
OAI-NSSF     component branch : master
OAI-LMF      component branch : master
OAI-AMF      component branch : master
OAI-NEF      component branch : master
OAI-UPF-VPP  component branch : master
OAI-UDM      component branch : master
OAI-UDR      component branch : master
OAI-AUSF     component branch : master
---------------------------------------------------------
[INFO] Cleaning existing submodules...
[INFO] No branches specified — cleaning only
```

## If you are using the `develop` images ##

If you want to pull the `develop` tags of the published images:

```bash
#!/bin/bash
docker pull oaisoftwarealliance/oai-amf:develop
docker pull oaisoftwarealliance/oai-nrf:develop
docker pull oaisoftwarealliance/oai-upf:develop
docker pull oaisoftwarealliance/oai-smf:develop
docker pull oaisoftwarealliance/oai-udr:develop
docker pull oaisoftwarealliance/oai-udm:develop
docker pull oaisoftwarealliance/oai-ausf:develop
docker pull oaisoftwarealliance/oai-upf-vpp:develop
docker pull oaisoftwarealliance/oai-nssf:develop
docker pull oaisoftwarealliance/oai-pcf:develop
docker pull oaisoftwarealliance/oai-nef:develop
docker pull oaisoftwarealliance/oai-lmf:develop
# Utility image to generate traffic
docker pull oaisoftwarealliance/trf-gen-cn5g:latest
```

You are ready to [Configure the Containers](./CONFIGURATION.md).

You can also go [back](./DEPLOY_HOME.md) to the list of tutorials.
