chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "scrape") {
        // Yeh ek basic example hai. Aap isko behtar bana sakte hain.
        const data = {
            name: document.title, // Example: page ke title ko name banayein
            email: '', // Email dhoondna mushkil hota hai, iske liye specific logic chahiye
            company: window.location.hostname, // Example: domain ko company banayein
            industry: ''
        };
        
        // LinkedIn ke liye thori behtar logic
        if(window.location.hostname.includes('linkedin.com')) {
            const nameElement = document.querySelector('h1');
            if (nameElement) {
                data.name = nameElement.textContent.trim();
            }
        }
        
        sendResponse({ data: data });
    }
    return true; // Asynchronous response ke liye zaroori hai
});