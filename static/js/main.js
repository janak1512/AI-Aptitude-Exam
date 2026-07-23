console.log("AI Aptitude Exam Loaded Successfully");

(function () {
    var drawer = document.getElementById("appNavCollapse");
    var toggler = document.getElementById("sidebarToggler") || document.querySelector(".sidebar-toggler");
    var backdrop = document.getElementById("sidebarBackdrop");
    var closeBtn = document.getElementById("sidebarDrawerClose");

    if (!drawer || !toggler) {
        return;
    }

    function isMobileNav() {
        return window.matchMedia("(max-width: 992px)").matches;
    }

    function setBodyScrollLocked(locked) {
        if (locked) {
            document.body.classList.add("nav-drawer-open");
            document.documentElement.classList.add("nav-drawer-open");
        } else {
            document.body.classList.remove("nav-drawer-open");
            document.documentElement.classList.remove("nav-drawer-open");
        }
    }

    function openDrawer() {
        if (!isMobileNav()) {
            return;
        }
        drawer.classList.add("is-open", "show");
        drawer.setAttribute("aria-hidden", "false");
        toggler.setAttribute("aria-expanded", "true");
        if (backdrop) {
            backdrop.hidden = false;
            requestAnimationFrame(function () {
                backdrop.classList.add("is-visible");
            });
        }
        setBodyScrollLocked(true);
    }

    function closeDrawer() {
        drawer.classList.remove("is-open", "show");
        drawer.setAttribute("aria-hidden", "true");
        toggler.setAttribute("aria-expanded", "false");
        if (backdrop) {
            backdrop.classList.remove("is-visible");
            window.setTimeout(function () {
                if (!drawer.classList.contains("is-open")) {
                    backdrop.hidden = true;
                }
            }, 280);
        }
        setBodyScrollLocked(false);
    }

    function toggleDrawer() {
        if (drawer.classList.contains("is-open")) {
            closeDrawer();
        } else {
            openDrawer();
        }
    }

    toggler.addEventListener("click", function (event) {
        event.preventDefault();
        if (!isMobileNav()) {
            return;
        }
        toggleDrawer();
    });

    if (closeBtn) {
        closeBtn.addEventListener("click", function () {
            closeDrawer();
        });
    }

    if (backdrop) {
        backdrop.addEventListener("click", function () {
            closeDrawer();
        });
    }

    drawer.querySelectorAll("a.nav-link, a").forEach(function (link) {
        link.addEventListener("click", function () {
            if (isMobileNav()) {
                closeDrawer();
            }
        });
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && drawer.classList.contains("is-open")) {
            closeDrawer();
        }
    });

    window.addEventListener("resize", function () {
        if (!isMobileNav() && drawer.classList.contains("is-open")) {
            closeDrawer();
        }
    });
})();
