------------------------------------------------------------------------------

                             OPENAIR-CN-5G
 An implementation of the 5G Core network by the OpenAirInterface community.

------------------------------------------------------------------------------

OPENAIR-CN-5G is an implementation of the 3GPP specifications for the 5G Core Network.
At the moment, it contains the following network elements:

* Access and Mobility Management Function (**AMF**)
* Authentication Server Management Function (**AUSF**)
* Location Management Function (**LMF**)
* Network Exposure Function (**NEF**)
* Network Slicing Selection Function (**NSSF**)
* Network Repository Function (**NRF**)
* Network Data Analytics Function (**NWDAF**)
* Policy Control Function (**PCF**)
* Session Management Function (**SMF**)
* Unified Data Management (**UDM**)
* Unified Data Repository (**UDR**)
* Unstructured Data Storage Function (**UDSF**)
* User Plane Function (**UPF**)

Each has its own repository: this repository (`oai-cn5g-amf`) is meant for AMF.

# Licence info

It is distributed under `OAI Public License V1.1`.
See [OAI Website for more details](https://www.openairinterface.org/?page_id=698).

The text for `OAI Public License V1.1` is also available under [LICENSE](LICENSE)
file at the root of this repository.

# Where to start

The Openair-CN-5G AMF code is written, executed, and tested on UBUNTU server bionic version.
Other Linux distributions support will be added later on.

More details on the supported feature set is available on this [page](docs/FEATURE_SET.md).

# Collaborative work

This source code is managed through a GITLAB server, a collaborative development platform:

*  URL: [https://gitlab.eurecom.fr/oai/cn5g/oai-cn5g-amf](https://gitlab.eurecom.fr/oai/cn5g/oai-cn5g-amf).

Process is explained in [CONTRIBUTING](CONTRIBUTING.md) file.

# Contribution requests

In a general way, anybody who is willing can contribute on any part of the
code in any network component.

Contributions can be simple bugfixes, advices and remarks on the design,
architecture, coding/implementation.

# Release Notes

They are available on the [CHANGELOG](CHANGELOG.md) file.

# IDS Lab Notes

This AMF is used in the IDS/NWDAF minikube lab. PacketRusher may sometimes
print:

```text
[UE][NAS] UE received a 5GMM Failure, cause: Illegal UE
```

In this codebase, `Illegal UE` can be emitted by AMF as a generic fallback for
several registration/authentication failures, not only for a permanently
unknown subscriber. The AMF now logs a diagnostic line before each known
`Illegal UE` registration reject path:

```bash
kubectl -n oai-5g-core logs deploy/oai-amf | rg "IDS-LAB-DIAG Illegal UE reject"
```

The diagnostic line includes:

- `site`: AMF function that selected the reject cause.
- `reason`: local failure path, such as `find_ue_context_failed`,
  `nas_context_not_available`, `auth_vectors_generation_failed`,
  `nas_context_lookup_failed`, or `authentication_validation_failed`.
- `ran_ue_ngap_id` and `amf_ue_ngap_id`: identifiers to correlate with
  PacketRusher and NGAP logs.
- `imsi` and `supi`: present when AMF already decoded the UE identity.
- `ctx_available` and `auth_vectors_present`: NAS context state when the
  reject was selected.

If the same IMSI is always rejected and the diagnostic reason points to
authentication vector generation, check the MySQL subscriber rows and SQN/key
data. If the rejected IMSI later registers successfully, treat the event as an
intermittent AMF context/authentication timing issue and correlate the
diagnostic IDs with PacketRusher startup timing.
