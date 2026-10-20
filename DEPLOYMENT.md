# Updating the installed plugin

1. Run lint, compileall and pytest; push the reviewed commit and wait for Python 3.13 CI.
2. Resolve the ComfyUI container and Portainer endpoint by name. Inspect queue state and finish
   active image jobs before restarting. Keep the existing environment, credentials and network.
3. Update the repository under the persistent custom_nodes mount. For archive-installed copies
   without `.git`, back up the existing directory and extract `git archive <commit>` into that exact
   plugin directory via Docker's container archive API. Do not extract over the ComfyUI root.
4. Restart only ComfyUI through Portainer. Verify the container is running and `/object_info`
   includes the Lemio node IDs. The host custom_nodes bind mount makes these files persistent.
5. Copy the example canvas into the user's saved workflow directory only after preserving their
   existing workflow. Reopen it and verify direction/feedback widgets and every graph link.
6. Execute a small actual workflow through the ComfyUI prompt queue, then verify history reports
   success, the preview is bounded, and the archive has matching image SHA-256 and manifest version 2.

The final quality check is built into Natural Retouch and therefore also protects old canvases.
Version-2 manifests require downstream readers to use `develop` rather than flat parameter keys.
Do not print environment variables, credential headers or image contents during deployment.

For rollback, restore the backed-up plugin files or deploy the prior commit, then restart ComfyUI.
Keep existing inputs, working JPEGs, final images, saved workflows and archives.
