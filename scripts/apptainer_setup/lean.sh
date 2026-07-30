# Step 1. pull the lean image
apptainer pull lean.sif docker://leanprovercommunity/lean4

# Step 2. Create the main folder and download the specific Lean 4 release (Linux version)
mkdir -p elan_home
cd elan_home

wget https://github.com/leanprover/lean4/releases/download/v4.25.0-rc2/lean-4.25.0-rc2-linux.tar.zst

tar -xvf lean-4.25.0-rc2-linux.tar.zst
mv lean-4.25.0-rc2-linux lean_bin


# Step 3. Create the project folder
mkdir ../lean_project
cd ../lean_project

# Step 4. Run 'lake init' with the math template
# We bind your host toolchain so 'lake' uses IT to generate the config
apptainer exec \
  --bind $PWD/../elan_home/lean_bin:/lean \
  --env PATH="/lean/bin:$PATH" \
  ../lean.sif \
  lake init my_project math

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