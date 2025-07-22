// 4. popup.js (Updated)
// Ismein API_URL ki ahem ghalti theek kar di gayi hai.

document.addEventListener('DOMContentLoaded', () => {
    // Views
    const loginView = document.getElementById('login-view');
    const scraperView = document.getElementById('scraper-view');

    // Login elements
    const loginEmailInput = document.getElementById('login-email');
    const loginPasswordInput = document.getElementById('login-password');
    const loginBtn = document.getElementById('login-btn');
    const logoutBtn = document.getElementById('logout-btn');

    // Scraper elements
    const nameInput = document.getElementById('name');
    const emailInput = document.getElementById('email');
    const companyInput = document.getElementById('company');
    const industryInput = document.getElementById('industry');
    const scrapeBtn = document.getElementById('scrape-btn');
    const sendBtn = document.getElementById('send-btn');
    const statusEl = document.getElementById('status');
    const deepSearchBtn = document.getElementById('deep-search-btn');

    // =================================================================
    // BUG FIX: URL format ko theek kar diya gaya hai. Yeh asal masla tha.
    const API_URL = '[http://127.0.0.1:5002](http://127.0.0.1:5002)'; 
    // =================================================================

    // UI ko login state ke hisaab se update karein
    const updateUiForLoginState = (isLoggedIn) => {
        if (isLoggedIn) {
            loginView.classList.add('hidden');
            scraperView.classList.remove('hidden');
        } else {
            loginView.classList.remove('hidden');
            scraperView.classList.add('hidden');
        }
    };

    // Shuru mein login state check karein
    chrome.storage.local.get(['idToken'], (result) => {
        updateUiForLoginState(!!result.idToken);
    });

    // Login button ka logic
    loginBtn.addEventListener('click', async () => {
        const email = loginEmailInput.value;
        const password = loginPasswordInput.value;
        if (!email || !password) {
            statusEl.textContent = 'Email aur password zaroori hain.';
            statusEl.style.color = 'red';
            return;
        }
        statusEl.textContent = 'Login kiya ja raha hai...';
        statusEl.style.color = 'gray';

        chrome.runtime.sendMessage({ action: "manual-login", data: { email, password } }, (response) => {
            if (response && response.success) {
                statusEl.textContent = '✅ Login kamyab!';
                statusEl.style.color = 'green';
                updateUiForLoginState(true);
            } else {
                statusEl.textContent = `Error: ${response.error || 'Login fail ho gaya.'}`;
                statusEl.style.color = 'red';
            }
        });
    });

    // Logout button ka logic
    logoutBtn.addEventListener('click', () => {
        try {
            chrome.runtime.sendMessage({ action: "logout" }, (response) => {
                if (chrome.runtime.lastError) {
                    // Handle runtime error (e.g., background script not available)
                    console.error(chrome.runtime.lastError.message);
                    statusEl.textContent = 'Error: Logout ke liye background script se rabta nahi ho saka.';
                    statusEl.style.color = 'red';
                    return;
                }

                if (response && response.success) {
                    statusEl.textContent = 'Logout kamyab.';
                    statusEl.style.color = 'gray';
                    updateUiForLoginState(false);
                } else {
                    statusEl.textContent = `Error: ${response.error || 'Logout fail ho gaya.'}`;
                    statusEl.style.color = 'red';
                }
            });
        } catch (error) {
            statusEl.textContent = `Error: ${error.message}`;
            statusEl.style.color = 'red';
        }
    });

    // Token haasil karne ka function
    async function getAuthToken() {
        return new Promise(resolve => chrome.storage.local.get(['idToken'], result => resolve(result.idToken)));
    }

    // "Extract Info" button ka logic
    scrapeBtn.addEventListener('click', async () => {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        chrome.tabs.sendMessage(tab.id, { action: "scrape" }, (response) => {
            if (chrome.runtime.lastError) {
                statusEl.textContent = 'Page ko refresh karke dobara try karein.';
                statusEl.style.color = 'red';
                return;
            }
            if (response && response.data) {
                nameInput.value = response.data.name || '';
                emailInput.value = response.data.email || '';
                companyInput.value = response.data.company || '';
                industryInput.value = response.data.industry || '';
                statusEl.textContent = '✨ Information nikal li gayi hai!';
                statusEl.style.color = '#0052cc';
            } else {
                statusEl.textContent = 'Information nahi mil saki.';
                statusEl.style.color = 'red';
            }
        });
    });

    // API call karne wala function
    async function performApiCall(endpoint, data) {
        statusEl.textContent = 'Bhej raha hai...';
        statusEl.style.color = 'gray';
        try {
            const idToken = await getAuthToken();
            if (!idToken) throw new Error("Aap login nahi hain. Pehle login karein.");
            
            const response = await fetch(`${API_URL}${endpoint}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${idToken}` },
                body: JSON.stringify(data)
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Server se error aya.');
            return result;
        } catch (error) {
            statusEl.textContent = `Error: ${error.message}`;
            statusEl.style.color = 'red';
            return null;
        }
    }

    // "Send to Dashboard" button ka logic
    sendBtn.addEventListener('click', async () => {
        const leadData = {
            'client name': nameInput.value, 'email': emailInput.value,
            'company / website': companyInput.value, 'industry': industryInput.value, 'score': 0
        };
        if (!leadData['client name']) {
            statusEl.textContent = 'Client ka naam zaroori hai.';
            statusEl.style.color = 'red';
            return;
        }
        const result = await performApiCall('/api/leads', leadData);
        if (result) {
            statusEl.textContent = '✅ Lead dashboard mein bhej diya gaya hai!';
            statusEl.style.color = 'green';
        }
    });

    // "Deep Search" button ka logic
    deepSearchBtn.addEventListener('click', async () => {
        const searchData = { name: nameInput.value, domain: companyInput.value };
        if (!searchData.name || !searchData.domain) {
            statusEl.textContent = 'Naam aur Company dono zaroori hain.';
            statusEl.style.color = 'red';
            return;
        }
        statusEl.textContent = 'Email dhoond raha hai...';
        statusEl.style.color = '#ff991f';
        const result = await performApiCall('/api/deep-search', searchData);
        if (result) {
            if (result.email) {
                emailInput.value = result.email;
                statusEl.textContent = '✅ Email mil gaya!';
                statusEl.style.color = 'green';
            } else {
                statusEl.textContent = '❌ Koi email nahi mila.';
                statusEl.style.color = 'red';
            }
        }
    });
}