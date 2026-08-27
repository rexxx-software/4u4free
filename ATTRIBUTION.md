# Attribution

4u4free is developed and maintained by **rexxx**. The project incorporates,
bundles, or interoperates with third-party software whose authors retain
copyright in their work. This file records the main sources; component-specific
license texts are stored in `third_party_licenses/` and alongside bundled files.

## SteaMidra / SFF

Parts of the integrated compatibility layer are derived from or based on
[SteaMidra / SFF](https://github.com/Midrags/SFF), created by Midrag and his
brother and released under GPL-3.0. The integration was based on upstream
release 6.6.6 and commit `fa44fc96b609c4cbe553e7e1e6ffd946de55b76f`.

SteaMidra itself credits Kur0, the SMD / Steam Manifest Downloader project, and
its contributors for its early project structure and workflow. Those credits
remain in effect for any inherited material.

## IBM Plex Sans

The desktop interface bundles IBM Plex Sans from the official
[IBM Plex repository](https://github.com/IBM/plex). Copyright 2017 IBM Corp.
The font is distributed under the SIL Open Font License 1.1; the license is
included at `four_u_four_free/assets/fonts/OFL.txt`.

## Steam Achievement Manager

The Windows build bundles the official Steam Achievement Manager 7.0.41 release
by Rick (gibbed):

- Project: <https://github.com/gibbed/SteamAchievementManager>
- Release: <https://github.com/gibbed/SteamAchievementManager/releases/tag/7.0.41>
- Source commit: `de8b71048a0cee3c3e97cd8535e0f55ca86513e4`
- Release archive SHA-256: `6682a3330604aaf31f6916ddbf3b78251abda3a019d15a53b1ce33b72d5cd072`
- License: zlib; included at `third_party/steam-achievement-manager/LICENSE.txt`

The separate `4u4free.PlaytimeIdler.exe` helper is built from source in
`tools/playtime_idler/` and is licensed under GPL-3.0-or-later. It dynamically
uses the unmodified zlib-licensed `SAM.API.dll`. Additional provenance is
recorded in `third_party/steam-achievement-manager/PLAYTIME_IDLER_SOURCE.txt`.

## SteamDB File Detection Rule Sets

Compatibility checks use selected rules from the MIT-licensed
[SteamDB File Detection Rule Sets](https://github.com/SteamDatabase/FileDetectionRuleSets):

- Pinned commit: `243cf741921d2c8fd6b844f83831edf4692cf788`
- License: MIT; included at `third_party/steamdb-file-detection/LICENSE`
- File hashes and source details: `third_party/steamdb-file-detection/SOURCE.txt`

These rules provide heuristic detections and do not guarantee compatibility.

## Other components

The repository contains or supports components including LumaCore, CreamAPI,
SmokeAPI, ScreamAPI, Uplay unlockers, gbe_fork, Steamless, SteamAutoCrack,
DepotDownloaderMod, rclone, Ludusavi data, SLSsteam/SLScheevo, and related
utilities. Each component remains under its original authorship, license, and
service terms. The detailed inventory and license texts are in
`third_party_licenses/`, `docs/Third-party notices.md`, and the relevant
component directories.

4u4free's GPL license covers 4u4free source and GPL-derived source. It does not
replace a third-party component's license or imply ownership of that component.
If a notice is missing or inaccurate, open an issue identifying the exact file,
source project, and correction.
