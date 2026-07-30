## Environment Setup

## Setting up verifiers

Create a common folder that stores all the images, all the used compilers, etc

```bash
mkdir -p apptainer_imgs
```

### Dafny

Just pull the pre-build image from the web. This image use Dafny 4.11

```bash
cd apptainer_imgs
apptainer pull dafny.sif docker://xtrm0/dafny
```

### Rust+verus

Similar to Dafny, we first pull the pre-build image from the web.

```bash
# cd apptainer_imgs if not in apptainer_imgs folder
apptainer pull verus.sif docker://ghcr.io/principled-systems/verus
```

Next, create folders to store the necessary toolchain files

```bash
mkdir -p rust_home/cargo
mkdir -p rust_home/toolchains
```

Run the installer to solve the version issue

```bash
apptainer exec \
  --bind $PWD/rust_home/cargo:/rust/cargo \
  --bind $PWD/rust_home/toolchains:/rust/toolchains \
  --env CARGO_HOME=/rust/cargo \
  --env RUSTUP_HOME=/rust/toolchains \
  verus.sif \
  bash -c "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain 1.79.0"
```

The whole script can be found at `script/verus.sh`

### Lean

For Lean, we focus on version 4.25.0-rc2

We first pull the image and setup folder

```bash
# Step 1. pull the lean image
# cd apptainer_imgs if not in apptainer_imgs folder
apptainer pull lean.sif docker://leanprovercommunity/lean4
```

Then, we manually download the Lean compiler with version 4.25.0-rc2, which will create a folder `elan_home` folder

```bash
# Step 2. Create the main folder and download the specific Lean 4 release (Linux version)
mkdir -p elan_home
cd elan_home

wget https://github.com/leanprover/lean4/releases/download/v4.25.0-rc2/lean-4.25.0-rc2-linux.tar.zst

tar -xvf lean-4.25.0-rc2-linux.tar.zst
mv lean-4.25.0-rc2-linux lean_bin
```

Next, we create the lean project and build Mathlib. The download will first pull the Mathlib using latest Lean

```bash
# Step 3. Create the project folder
mkdir lean_project
cd lean_project

# Step 4. Run 'lake init' with the math template
# We bind your host toolchain so 'lake' uses IT to generate the config
apptainer exec \
  --bind $PWD/../elan_home/lean_bin:/lean \
  --env PATH="/lean/bin:$PATH" \
  ../lean.sif \
  lake init my_project math
```

We need to edit the lakefile, to match our manually downloaded lean compiler (version 4.25.0-rc2)

```bash
# Step 5. Edit lakefile to match lean version

cat <<EOF > lakefile.lean
import Lake
open Lake DSL

package "my_project" where
  -- settings...

lean_lib «MyProject» where
  -- settings...

require mathlib from git
  "https://github.com/leanprover-community/mathlib4" @ "v4.25.0-rc2"
EOF

# Step 6. Update. It is normal to see the error message in the end, just proceed to the next step

apptainer exec \
  --bind $PWD/../elan_home/lean_bin:/lean \
  --env PATH="/lean/bin:$PATH" \
  ../lean.sif \
  lake update
```

Note that it is common to see an error message. Just proceed with overriding the lean version, fetch the cache, and build

```bash
# Step 7. Override lean version and get files
cp .lake/packages/mathlib/lean-toolchain ./lean-toolchain

apptainer exec \
  --bind $PWD/../elan_home/lean_bin:/lean \
  --env PATH="/lean/bin:$PATH" \
  ../lean.sif \
  lake exe cache get

# Step 8. Build Mathlib

apptainer exec \
  --bind $PWD/../elan_home/lean_bin:/lean \
  --env PATH="/lean/bin:$PATH" \
  ../lean.sif \
  lake build

rm lakefile.toml
```

### Test the verifiers

First set up the config file in test/ folder (e.g. copying config_test.yaml or config_jiawei_test.yaml) and modify the paths. Then run the following (change to your config file in the code)

```bash
python -m test.test_dafny_verify.py
python -m test.test_lean_verify.py
python -m test.test_verus_verify.py
```
