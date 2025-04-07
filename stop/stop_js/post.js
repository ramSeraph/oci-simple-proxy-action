const core = require('@actions/core');
const { spawn } = require("child_process");

function run(cmd) {
  const subprocess = spawn(cmd, { stdio: "inherit", shell: true });
  subprocess.on("exit", (exitCode) => {
    process.exitCode = exitCode;
  });
}

try {
  const action_dir = process.env.GITHUB_ACTION_PATH;

  const ociCompartmentName = core.getInput('oci-compartment-name');
  const ociNameSuffix = core.getInput('oci-name-suffix');

  run(`uv run --with=oci ${action_dir}/stop/stop_js/stop.py --config-file='.oci/config' --name-suffix=${ociNameSuffix} --compartment-name=${ociCompartmentName}`);

} catch (error) {
  core.setFailed(error.message);
}



