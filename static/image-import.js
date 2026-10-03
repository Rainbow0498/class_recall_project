"use strict";
(() => {
  const errors = document.querySelector(".import-errors");
  if (errors) errors.focus();
  const upload = document.querySelector("#image-upload-form");
  if (upload) {
    const input = upload.querySelector('input[type="file"]');
    const preview = document.querySelector("#local-image-preview");
    let url;
    input.addEventListener("change", () => {
      if (url) URL.revokeObjectURL(url);
      const file = input.files[0];
      input.setCustomValidity(file && file.size > 6 * 1024 * 1024 ? "图片不能超过 6 MB。" : "");
      preview.hidden = !file || !file.type.startsWith("image/");
      if (!preview.hidden) {
        url = URL.createObjectURL(file);
        preview.querySelector("img").src = url;
      }
    });
    upload.addEventListener("submit", () => {
      const button = document.querySelector("#recognize-image");
      button.disabled = true; button.textContent = "正在识别…";
      document.querySelector("#image-upload-status").textContent = "正在读取学生、日期和时段，请稍候。识别完成后可以核对修改。";
    });
    window.addEventListener("pageshow", () => {
      const button = document.querySelector("#recognize-image");
      if (button.textContent === "正在识别…") { button.disabled = false; button.textContent = "识别课表图片"; }
    });
  }
  document.querySelectorAll(".import-row").forEach(row => {
    const include = row.querySelector('input[type="checkbox"]');
    const start = row.querySelector('input[type="time"]');
    const name = row.querySelector('input[name$="-name"]');
    const student = row.querySelector('select[name$="-student"]');
    function update() {
      row.classList.toggle("is-excluded", !include.checked);
      let label = "2 小时";
      start.setCustomValidity("");
      if (start.value) {
        const [hour, minute] = start.value.split(":").map(Number);
        const value = hour * 60 + minute + 120;
        const end = String(Math.floor(value / 60) % 24).padStart(2, "0") + ":" + String(value % 60).padStart(2, "0");
        label = start.value + "–" + (value >= 1440 ? "次日 " : "") + end;
        start.setCustomValidity(include.checked && value >= 1440 ? "2 小时课程不能跨日，请调整开始时间。" : "");
      }
      row.querySelector(".import-end").textContent = label;
    }
    include.addEventListener("change", update); start.addEventListener("input", update);
    name.addEventListener("input", () => { student.value = ""; });
    student.addEventListener("change", () => {
      if (student.value) name.value = student.selectedOptions[0].dataset.name;
    });
    update();
  });
})();
