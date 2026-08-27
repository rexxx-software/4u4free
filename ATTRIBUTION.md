# Attribution

4u4free is developed and maintained by **rexxx**. The project includes a small
amount of adapted open-source code and several unmodified runtime components.
Their original authors retain copyright and their original licenses continue to
apply.

## Internal compatibility code

Files under `four_u_four_free/_compat/` are the subset required by 4u4free from
[SteaMidra / SFF](https://github.com/Midrags/SFF), created by Midrag and
contributors and released under GPL-3.0. The integration was based on upstream
release 6.6.6 and commit `fa44fc96b609c4cbe553e7e1e6ffd946de55b76f`.
Copyright and GPL notices are retained in the adapted source files.

## IBM Plex Sans

The desktop interface bundles IBM Plex Sans from the
[IBM Plex repository](https://github.com/IBM/plex). Copyright 2017 IBM Corp.
The font is distributed under the SIL Open Font License 1.1; the license is at
`four_u_four_free/assets/fonts/OFL.txt`.

## Steam Achievement Manager

The Windows installer includes the official Steam Achievement Manager 7.0.41
runtime by Rick (gibbed), sourced from commit
`de8b71048a0cee3c3e97cd8535e0f55ca86513e4`. It is distributed under the zlib
license at `third_party/steam-achievement-manager/LICENSE.txt`.

The `4u4free.PlaytimeIdler.exe` helper is built from source in
`tools/playtime_idler/` and dynamically uses the unmodified `SAM.API.dll`.
Provenance and checksums are stored beside the bundled files.

## SteamDB File Detection Rule Sets

Compatibility checks use rules from the MIT-licensed
[SteamDB File Detection Rule Sets](https://github.com/SteamDatabase/FileDetectionRuleSets),
pinned to commit `243cf741921d2c8fd6b844f83831edf4692cf788`. The license and
source record are stored in `third_party/steamdb-file-detection/`.

## Steamless

The installer includes the unmodified Steamless command-line runtime by atom0s
for user-initiated SteamStub maintenance. Steamless remains under its original
license, included at `third_party_licenses/steamless.LICENSE`.

## DLC compatibility resources

The installer includes unmodified runtime resources for CreamAPI, SmokeAPI, and
Uplay R1/R2 compatibility. These binaries remain the work of their respective
authors and are used only when the user explicitly selects the corresponding
feature. 4u4free does not claim ownership of these components.

4u4free's GPL license covers 4u4free source and GPL-derived source. It does not
replace any third-party license or imply ownership of a third-party component.
Please open an issue if a notice needs correction.
