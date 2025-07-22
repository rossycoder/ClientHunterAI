
import { initializeApp } from "https://www.gstatic.com/firebasejs/11.6.1/firebase-app.js";
import { getAuth, signInWithEmailAndPassword, signOut, onAuthStateChanged, getIdToken } from "https://www.gstatic.com/firebasejs/11.6.1/firebase-auth.js";

let auth;

try {
    const firebaseConfig = {
        apiKey: "AIzaSyCerSZpilFHxS3cB4BUqTricn2xLeAm3gc",
        authDomain: "client-hunter-app.firebaseapp.com",
        projectId: "client-hunter-app",
        storageBucket: "client-hunter-app.appspot.com",
        messagingSenderId: "594541822555",
        appId: "1:594541822555:web:a7426b558a043948e3b57e"
    };
    const app = initializeApp(firebaseConfig);
    auth = getAuth(app);
    console.log("Background: Firebase initialized successfully.");
} catch (e) {
    console.error("CRITICAL: Firebase initialization failed in background script.", e);
}

if (auth) {
    // Popup se anay walay messages ko sunein
    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
        if (request.action === "manual-login") {
            const { email, password } = request.data;
            signInWithEmailAndPassword(auth, email, password)
                .then(async (userCredential) => {
                    const idToken = await getIdToken(userCredential.user, true);
                    chrome.storage.local.set({ idToken: idToken }, () => {
                        sendResponse({ success: true, token: idToken });
                    });
                })
                .catch(error => {
                    sendResponse({ success: false, error: error.message });
                });
            return true; // Asynchronous response ke liye zaroori hai
        }
        else if (request.action === "logout") {
            signOut(auth).then(() => {
                chrome.storage.local.remove('idToken', () => {
                    sendResponse({ success: true });
                });
            }).catch(error => {
                sendResponse({ success: false, error: error.message });
            });
            return true; // Asynchronous response ke liye zaroori hai
        }
    });

    // Login state change hone par token ko update karein
    onAuthStateChanged(auth, async (user) => {
        if (user) {
            const idToken = await getIdToken(user, true);
            chrome.storage.local.set({ idToken: idToken });
        } else {
            chrome.storage.local.remove('idToken');
        }
    });
}