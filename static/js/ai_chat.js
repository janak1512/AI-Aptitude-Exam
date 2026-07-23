document.getElementById("sendBtn").addEventListener("click", sendMessage);


document.getElementById("userMessage")
.addEventListener("keypress", function(e){

    if(e.key === "Enter"){
        sendMessage();
    }

});



function sendMessage(){


    let input = document.getElementById("userMessage");

    let message = input.value.trim();



    if(message === "")
        return;



    let chatBox = document.getElementById("chatBox");



    // USER MESSAGE

    chatBox.innerHTML += `

        <div class="message user-message">

            ${message}

        </div>

    `;



    input.value = "";



    // Scroll bottom

    chatBox.scrollTop = chatBox.scrollHeight;



    // Typing indicator

    chatBox.innerHTML += `

        <div class="typing" id="typing">

            🤖 AI is thinking...

        </div>

    `;



    fetch("/ai_chat",{


        method:"POST",


        headers:{

            "Content-Type":"application/json"

        },


        body:JSON.stringify({

            message:message,

            company: (document.getElementById("userMessage").getAttribute("data-target-company") || "")

        })


    })



    .then(response=>response.json())



    .then(data=>{


        document.getElementById("typing").remove();



        chatBox.innerHTML += `


        <div class="message ai-message">

            ${data.reply}

        </div>


        `;



        chatBox.scrollTop = chatBox.scrollHeight;



    })



    .catch(error=>{


        document.getElementById("typing").remove();



        chatBox.innerHTML += `

        <div class="message ai-message">

            ❌ AI service unavailable.

        </div>

        `;


    });



}