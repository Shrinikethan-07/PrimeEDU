const DISTRACTING_SITES = [
    'youtube.com',
    'facebook.com',
    'instagram.com',
    'twitter.com',
    'netflix.com'
];

chrome.webNavigation.onBeforeNavigate.addListener((details) => {
    if (details.frameId !== 0) return;

    const url = new URL(details.url);
    const isDistracting = DISTRACTING_SITES.some(site => url.hostname.includes(site));

    if (isDistracting) {
        // Redirection logic to your FocusForge landing page
        // For local development, this would be the path to index.html
        chrome.tabs.update(details.tabId, {
            url: "https://focusforge.vercel.app/regain-penalty" // Example URL
        });

        // Deduction logic (communicating with the main app)
        console.log("Distraction detected. Points deduction recommended.");
    }
});
