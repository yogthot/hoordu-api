
let COUNT = 20;
let NO_CACHE = true;

nunjucks.configure("/static/templates", {
    autoescape: true,
    trimBlocks: true,
    lstripBlocks: true,
});

function openWebsocket(endpoint) {
    var loc = window.location, new_uri;
    if (loc.protocol === "https:") {
        new_uri = "wss:";
    } else {
        new_uri = "ws:";
    }
    new_uri += "//" + loc.host + endpoint;
    return new WebSocket(new_uri);
}

function scheduler(task, concurrent){
    let resolvers = [];
    let promises = [];
    
    function add_task() {
        promises.push(new Promise(resolve => {
            resolvers.push(resolve);
        }));
    }
    
    function replace_task() {
        if(!resolvers.length)
            add_task();
        
        resolvers.shift()();
    }
    
    function get_task() {
        if(!promises.length)
            add_task();
        
        return promises.shift();
    }
    
    for (let i = 0; i < concurrent; i++) {
        add_task();
        resolvers.shift()();
    }
    
    return async (...args) => {
        await get_task();
        try {
            await task(...args);
        } catch(e) {
            console.error(e);
        }
        replace_task();
    };
}

// in miliseconds
var units = {
  year  : 24 * 60 * 60 * 1000 * 365,
  month : 24 * 60 * 60 * 1000 * 365/12,
  day   : 24 * 60 * 60 * 1000,
  hour  : 60 * 60 * 1000,
  minute: 60 * 1000,
  second: 1000,
};
var rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });
var getRelativeTime = (d1, d2 = new Date()) => {
    var elapsed = d1 - d2;
    
    for (var u in units)
        if (Math.abs(elapsed) > units[u] || u == 'second')
            return rtf.format(Math.round(elapsed/units[u]), u);
}

async function loadTemplate(address) {
    if (NO_CACHE) address += "?nocache=" + Date.now();
    let resp = await fetch(address);
    let text = await resp.text();
    return nunjucks.compile(text);
}

function renderWithEvents(template, data, callbacks) {
    let html = template.render(data);
    let cont = document.createElement("div");
    cont.innerHTML = html;
    let renderedElement = cont.firstElementChild;
    
    for (const [name, [eventName, callback]] of Object.entries(callbacks)) {
        let elements = renderedElement.querySelectorAll(`[data-event="${name}"]`);
        for (const element of elements) {
            element.addEventListener(eventName, function(event) {
                callback.call(this, event, data, renderedElement);
            });
        }
    }
    
    return renderedElement;
}

window.api = window.api || {};
(function(api) {
    api.renote = async function(note_id) {
        let params = new URLSearchParams({
            note_id: note_id,
        });
        await fetch("/renote?" + params);
    }
    api.react = async function(note_id, reaction) {
        if (reaction === undefined) {
            reaction = "❤";
        }
        let params = new URLSearchParams({
            note_id: note_id,
            reaction: reaction,
        });
        await fetch("/react?" + params)
    }
})(window.api);

window.addEventListener("load", async () => {
    let noteContainer = document.querySelector("#notes");
    
    let noteTemplate = await loadTemplate("/static/templates/note.html");
    
    
    let c = 0;
    var socket = openWebsocket("/timeline?count=" + COUNT);
    
    function handleMessage(message) {
        let note = JSON.parse(message.data);
        note.time_ago = getRelativeTime(new Date(note.note_time + "Z"));
        
        let callbacks = {
            renote: ["click", async function(event, data, element) {
                await api.renote(data.note.id);
                this.classList.add("reacted");
            }],
            
            react: ["click", async function(event, data, element) {
                await api.react(data.note.id);
                this.classList.add("reacted");
            }],
        };
        
        let elem = renderWithEvents(noteTemplate, {note: note}, callbacks);
        noteContainer.appendChild(elem);
        
        c++;
        if (c >= COUNT) {
            function loadMore(ev) {
                if ((window.innerHeight + window.scrollY) >= document.body.offsetHeight) {
                    window.removeEventListener("scroll", loadMore);
                    console.log("requesting more");
                    socket.send(JSON.stringify({"command": "continue"}));
                    c = 0;
                }
            }
            window.addEventListener("scroll", loadMore);
        }
    }
    socket.addEventListener("message", scheduler(handleMessage, 1));
});

