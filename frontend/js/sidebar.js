/** Sidebar toggle and global context-menu close, moved out of inline HTML. */
function toggleSidebar() {
    document.querySelector('.sidebar')?.classList.toggle('open');
    document.querySelector('.sidebar-overlay')?.classList.toggle('active');
}
window.toggleSidebar = toggleSidebar;

document.addEventListener('click', () => {
    const cm = document.getElementById('contextMenu');
    if (cm) cm.style.display = 'none';
});
