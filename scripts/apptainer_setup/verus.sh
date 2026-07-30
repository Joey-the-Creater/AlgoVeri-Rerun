# Step 1. pull the verus image
apptainer pull verus.sif docker://ghcr.io/principled-systems/verus

# Step 2. Create the main folder and the two subfolders
mkdir -p rust_home/cargo
mkdir -p rust_home/toolchains


# Step 3. Run the Installer
apptainer exec \
  --bind $PWD/rust_home/cargo:/rust/cargo \
  --bind $PWD/rust_home/toolchains:/rust/toolchains \
  --env CARGO_HOME=/rust/cargo \
  --env RUSTUP_HOME=/rust/toolchains \
  verus.sif \
  bash -c "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain 1.79.0"