console.log("AI Aptitude Exam Loaded Successfully");

(function () {
    var collapseEl = document.getElementById("appNavCollapse");
    var toggler = document.querySelector(".sidebar-toggler");
    if (!collapseEl || !toggler || typeof bootstrap === "undefined") {
        return;
    }

    var collapse = bootstrap.Collapse.getOrCreateInstance(collapseEl, {
        toggle: false
    });

    function isMobileNav() {
        return window.matchMedia("(max-width: 992px)").matches;
    }

    function closeMobileNav() {
        if (!isMobileNav() || !collapseEl.classList.contains("show")) {
            return;
        }
        collapse.hide();
    }

    collapseEl.querySelectorAll("a.nav-link, a").forEach(function (link) {
        link.addEventListener("click", function () {
            closeMobileNav();
        });
    });

    window.addEventListener("resize", function () {
        if (!isMobileNav() && collapseEl.classList.contains("show")) {
            collapse.hide();
        }
    });
})();
