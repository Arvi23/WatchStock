// Chat panel: messages, LLM round-trip, UI actions the model may request, resize.
// Plain script (not a module): all files share one global scope and load in the
// order listed in index.html. Top-level code may only call functions from earlier files.

// --- 6. CHAT & RESIZE LOGIC ---
const oldChatBar = document.getElementById('oldChatBar');
const oldChatInput = document.getElementById('oldChatInput');
const oldChatSendBtn = document.getElementById('oldChatSendBtn');

const rightChatPanel = document.getElementById('rightChatPanel');
const chatResizer = document.getElementById('chatResizer');
const closeRightChatBtn = document.getElementById('closeRightChatBtn');
const rightChatInput = document.getElementById('rightChatInput');
const rightChatSendBtn = document.getElementById('rightChatSendBtn');
const chatHistory = document.getElementById('chatHistory');
let conversationMessages = []; // Tracks full chat history for multi-turn LLM context

// Launch Right Chat Sequence
function triggerChatOpen(initialMsg) {
    if (!initialMsg) return;
    
    oldChatBar.style.display = 'none';
    rightChatPanel.style.display = 'flex';
    chatResizer.style.display = 'block';
    chatResizer.classList.remove('hidden');

    // Auto-switch to AI Analysis tab
    switchToAiTab();

    rightChatInput.focus();
    appendChatMessage("USER", initialMsg);
    sendChatToLLM(initialMsg);
}

function switchToAiTab() {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    const aiBtn = document.querySelector('.tab-btn[data-target="tab-ai"]');
    if (aiBtn) aiBtn.classList.add('active');
    const aiTab = document.getElementById('tab-ai');
    if (aiTab) aiTab.classList.add('active');
}

function appendChatMessage(role, text, isMarkdown) {
    const div = document.createElement('div');
    div.className = 'w-full flex-shrink-0 flex flex-col gap-1';
    
    const isUser = role === 'USER';
    
    const roleLabel = document.createElement('span');
    roleLabel.className = 'text-[10px] font-bold tracking-wider';
    roleLabel.style.color = isUser ? '#e0e0e0' : 'var(--accent)';
    roleLabel.innerText = role;

    const pBox = document.createElement('div');
    if (isUser) {
        pBox.className = 'p-3 text-sm font-light text-[#e0e0e0] bg-[#1a1a1a] border-l-2 border-[#555]';
        pBox.innerText = text;
        // Track user message for conversation history
        conversationMessages.push({ role: 'user', content: text });
    } else {
        pBox.className = 'p-3 text-sm text-[#e0e0e0] bg-[#121212] border border-[#333]';
        if (isMarkdown) {
            pBox.innerHTML = renderMarkdown(text);
        } else {
            pBox.innerText = text;
        }
    }

    div.appendChild(roleLabel);
    div.appendChild(pBox);
    chatHistory.appendChild(div);
    chatHistory.scrollTop = chatHistory.scrollHeight;
    return pBox;
}

async function sendChatToLLM(question) {
    // Show thinking indicator
    const thinkingBox = appendChatMessage("SYSTEM", "Analyzing...");
    thinkingBox.innerHTML = '<div class="flex items-center gap-2"><div class="spinner w-3 h-3 border-2"></div><span style="color:var(--text-muted); font-size:0.75rem;">Processing query...</span></div>';

    try {
        const result = await api('/api/chat', {
            method: 'POST',
            body: {
                question: question,
                stock: currentRawData,
                history: conversationMessages,
                existing_chart_titles: getExistingChartTitles(),
            },
        });

        if (!result) {
            thinkingBox.innerText = "No response.";
        } else {
            const replyText = result.reply_text || result.answer || "No response.";
            thinkingBox.innerHTML = renderMarkdown(replyText);
            conversationMessages.push({ role: 'assistant', content: replyText });

            // Handle ui_action — could be an object or nested inside reply
            let uiAction = result.ui_action;

            // Fallback: if LLM embedded action JSON in reply_text, try to extract it
            if (!uiAction && typeof replyText === 'string') {
                const actionMatch = replyText.match(/\{"action"\s*:\s*"[^"]+"/);
                if (actionMatch) {
                    try {
                        const jsonStart = replyText.indexOf(actionMatch[0]);
                        let depth = 0, end = jsonStart;
                        for (let i = jsonStart; i < replyText.length; i++) {
                            if (replyText[i] === '{') depth++;
                            if (replyText[i] === '}') depth--;
                            if (depth === 0) { end = i + 1; break; }
                        }
                        uiAction = JSON.parse(replyText.substring(jsonStart, end));
                    } catch(e) {}
                }
            }

            if (uiAction) {
                handleUiAction(uiAction);
            }
            // Support array of actions (ui_actions)
            if (result.ui_actions && Array.isArray(result.ui_actions)) {
                result.ui_actions.forEach(a => handleUiAction(a));
            }
        }
    } catch(err) {
        thinkingBox.innerText = "Error: " + err.message;
        thinkingBox.style.color = '#ff6b6b';
    }
    chatHistory.scrollTop = chatHistory.scrollHeight;
}

// Handle dynamic UI actions from chat LLM
function handleUiAction(action) {
    if (!action || !action.action) return;
    
    if (action.action === 'update_chart') {
        if (action.labels && action.values) {
            // Recreate the canvas if it isn't on the page yet
            let canvas = document.getElementById('dynamicChart');
            if (!canvas) {
                // Recreate the chart container inside AI analysis result
                const aiResult = document.getElementById('aiAnalysisResult');
                if (aiResult) {
                    const wrapper = document.createElement('div');
                    wrapper.className = 'pl-4 border-l-[3px]';
                    wrapper.style.borderLeftColor = 'var(--accent)';
                    wrapper.innerHTML = `
                        <h4 class="text-xs font-bold uppercase tracking-widest mb-4" style="color: var(--accent)">Dynamic Metric Plot</h4>
                        <div style="width: 100%; max-height: 280px; margin-top: 10px;">
                            <canvas id="dynamicChart"></canvas>
                        </div>`;
                    aiResult.appendChild(wrapper);
                    canvas = document.getElementById('dynamicChart');
                }
            }
            if (!canvas) return;

            if (dynamicChartInstance) dynamicChartInstance.destroy();
            dynamicChartInstance = createChart('dynamicChart', action);
            // Make sure AI result is visible and switch to AI tab
            document.getElementById('aiAnalysisResult')?.classList.remove('hidden');
            switchToAiTab();
        }
    } else if (action.action === 'switch_tab') {
        const targetTab = action.tab || 'tab-ai';
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        const btn = document.querySelector(`.tab-btn[data-target="${targetTab}"]`);
        if (btn) btn.classList.add('active');
        const tab = document.getElementById(targetTab);
        if (tab) tab.classList.add('active');
    } else if (action.action === 'search_company') {
        // LLM wants to search another company
        const newCompany = action.company_name || '';
        const newTicker = action.ticker || '';
        if (newCompany && newTicker) {
            appendChatMessage('SYSTEM', `Switching to ${newCompany} (${newTicker})...`);
            conversationMessages = [];
            companyInput.value = newCompany;
            tickerInput.value = newTicker;
            executeSearch(newCompany, newTicker);
        }
    } else if (action.action === 'append_new_chart') {
        // Append a brand-new chart to the AI Analysis tab (or specified tab)
        const cfg = action.chart_config || action;
        if (cfg.labels && cfg.values) {
            const tabMap = { 'tab-ai': 'aiAnalysisResult', 'tab-news': 'newsContent', 'ai-analysis': 'aiAnalysisResult' };
            const containerId = tabMap[action.target_tab] || 'aiAnalysisResult';
            const container = document.getElementById(containerId);
            if (!container) return;

            const uniqueId = 'dynamicChart_' + Date.now() + '_' + Math.random().toString(36).substr(2, 5);

            const wrapper = document.createElement('div');
            wrapper.className = 'pl-4 border-l-[3px] mt-8';
            wrapper.style.borderLeftColor = 'var(--accent)';
            wrapper.innerHTML = `
                <h4 class="text-xs font-bold uppercase tracking-widest mb-4" style="color: var(--accent)">${cfg.title || 'Chart'}</h4>
                <div style="width:100%; max-height:300px; margin-top:10px;">
                    <canvas id="${uniqueId}"></canvas>
                </div>`;
            container.appendChild(wrapper);
            container.classList.remove('hidden');

            createChart(uniqueId, cfg);
            switchToAiTab();
        }
    } else if (action.action === 'highlight_risk') {
        // Flash risk indicators
        const circles = [document.getElementById('sbStCircle'), document.getElementById('sbLtCircle')];
        circles.forEach(c => {
            if (c) {
                c.style.transition = 'transform 0.3s, box-shadow 0.3s';
                c.style.transform = 'scale(1.3)';
                c.style.boxShadow = '0 0 15px rgba(255,100,100,0.6)';
                setTimeout(() => { c.style.transform = 'scale(1)'; c.style.boxShadow = 'none'; }, 2000);
            }
        });
    }
}

// Force Update: bypass cache and re-fetch fresh data
oldChatSendBtn.addEventListener('click', () => {
    const val = oldChatInput.value.trim();
    if(val) { oldChatInput.value = ''; triggerChatOpen(val); }
});

oldChatInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        const val = oldChatInput.value.trim();
        if(val) { oldChatInput.value = ''; triggerChatOpen(val); }
    }
});

rightChatSendBtn.addEventListener('click', () => {
    const val = rightChatInput.value.trim();
    if(val) { 
        rightChatInput.value = ''; 
        appendChatMessage("USER", val); 
        sendChatToLLM(val);
    }
});

rightChatInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        const val = rightChatInput.value.trim();
        if(val) { 
            rightChatInput.value = ''; 
            appendChatMessage("USER", val); 
            sendChatToLLM(val);
        }
    }
});

closeRightChatBtn.addEventListener('click', () => {
    rightChatPanel.style.display = 'none';
    chatResizer.classList.add('hidden');
    oldChatBar.style.display = 'flex';
});

// --- DRAG TO RESIZE LOGIC ---
let isResizing = false;

chatResizer.addEventListener('mousedown', (e) => {
    e.preventDefault(); // Prevents defaults on mousedown
    isResizing = true;
    document.body.style.userSelect = 'none'; // Prevent text selection during resize
    document.body.style.cursor = 'col-resize';
});

document.addEventListener('mousemove', (e) => {
    if (!isResizing) return;
    
    // Right Panel is clamped on the right bounding box
    // Distance from Right Edge = Window Width - current MouseX
    let newWidth = window.innerWidth - e.clientX;
    
    // Clamp between 250px and 800px per specifications
    if (newWidth < 250) newWidth = 250;
    if (newWidth > 800) newWidth = 800;
    
    rightChatPanel.style.width = newWidth + 'px';
});

document.addEventListener('mouseup', () => {
    if (isResizing) {
        isResizing = false;
        document.body.style.userSelect = '';
        document.body.style.cursor = '';
    }
});
