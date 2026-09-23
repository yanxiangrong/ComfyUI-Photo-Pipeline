import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NODE_ID = "LemioUploadPhoto";
const ACCEPT = ".jpg,.jpeg,.png,.dng,.nef,.cr2,.cr3,.arw,.orf,.rw2,.raf,.pef,.srw";

app.registerExtension({
  name: "Lemio.PhotoPipeline.Upload",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_ID) return;
    const original = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const result = original?.apply(this, arguments);
      const refWidget = this.widgets?.find((widget) => widget.name === "source_ref");
      if (!refWidget) return result;
      refWidget.type = "text";
      refWidget.options = { ...(refWidget.options || {}), read_only: true };

      const fileInput = document.createElement("input");
      fileInput.type = "file";
      fileInput.accept = ACCEPT;
      fileInput.style.display = "none";
      document.body.appendChild(fileInput);

      const upload = async (file) => {
        const body = new FormData();
        body.append("photo", file, file.name);
        const response = await api.fetchApi("/lemio/photo-pipeline/upload", { method: "POST", body });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || `Upload failed (HTTP ${response.status})`);
        refWidget.value = payload.reference;
        refWidget.label = payload.filename;
        this.setDirtyCanvas(true, true);
      };

      fileInput.addEventListener("change", async () => {
        const file = fileInput.files?.[0];
        if (!file) return;
        try { await upload(file); } catch (error) { alert(`Lemio upload: ${error.message}`); }
        finally { fileInput.value = ""; }
      });
      this.addWidget("button", "Choose photo…", null, () => fileInput.click());
      this.onDragOver = () => true;
      this.onDragDrop = (event) => {
        const file = event.dataTransfer?.files?.[0];
        if (!file) return false;
        upload(file).catch((error) => alert(`Lemio upload: ${error.message}`));
        return true;
      };
      const removed = this.onRemoved;
      this.onRemoved = function () { fileInput.remove(); return removed?.apply(this, arguments); };
      return result;
    };
  },
});

