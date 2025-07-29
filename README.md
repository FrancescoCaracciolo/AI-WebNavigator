# AI WebNavigator

<p>
  <img align="left" width="300" src="https://github.com/user-attachments/assets/2bc5b4ca-dabc-4b9d-9092-5f0d21765fa5"/>

  <a href="https://github.com/topics/newelle-extension">
    <img width="100" alt="Download on Flathub" src="https://raw.githubusercontent.com/qwersyk/Assets/main/newelle-extension.svg"/>
  </a>
  <br/>
  <b>
    AI WebNavigator is a <a href="https://github.com/qwersyk/Newelle">Newelle</a> Extension that allows AI to navigate through websites: AI retrives data and uses it to deliver complete and reliable information.  
  </b>
  The user is always shown the specific webpage the piece of information was found on, making it easy to double check and verify AI's answers.
</p>

<br/><br/>

# Overview

https://github.com/user-attachments/assets/d4fb8711-ec76-46c9-8ba6-28889c4b6069

## Use Cases
* Get "summaries" of websites, wrapping them up
* Quickly find specific pieces of information in websites
* Get up to date data
* Find hidden resources in websites

## How does it work
1. The LLM has the ability to open the integrated Newelle Browser
2. The LLM can visit any link
3. When a link is visited, the web page is scraped and cleaned to only get the links and the relevant text in it
4. The LLM answers based on these information

The extension also support integration with buit-in Newelel RAG in order to provide relevant information about websites.

# Installation
- Download and Install [Newelle](https://flathub.org/apps/io.github.qwersyk.Newelle)
- Download the [python file](https://github.com/FrancescoCaracciolo/AI-WebNavigator/blob/main/webnavigator.py) in the repository
- Load the extension
![screenshot](https://raw.githubusercontent.com/qwersyk/Mathematical-graph/main/Screenshot.png)
