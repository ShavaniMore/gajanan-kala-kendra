/* Admin panel behaviour: mobile sidebar, confirm prompts, image preview */
document.addEventListener("DOMContentLoaded", () => {
    const side = document.getElementById("adSide");
    const scrim = document.getElementById("adScrim");
    const toggle = open => {
        side?.classList.toggle("open", open);
        scrim?.classList.toggle("open", open);
    };
    document.getElementById("adMenu")?.addEventListener("click", () => toggle(!side.classList.contains("open")));
    scrim?.addEventListener("click", () => toggle(false));

    /* <form data-confirm="Are you sure?"> asks before submitting (delete buttons etc.) */
    document.querySelectorAll("form[data-confirm]").forEach(form =>
        form.addEventListener("submit", e => {
            if (!window.confirm(form.dataset.confirm)) e.preventDefault();
        }));

    /* product form: live preview of the chosen photo */
    const file = document.getElementById("imageFile");
    const preview = document.getElementById("imagePreview");
    if (file && preview) {
        file.addEventListener("change", () => {
            const f = file.files && file.files[0];
            if (f) preview.src = URL.createObjectURL(f);
        });
    }
});
