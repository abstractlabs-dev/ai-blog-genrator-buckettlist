# The AI Blog Generator - Explained Simply

Think of this software as a **Smart Automated Factory** that produces high-quality blog posts instead of physical products. Here is how the factory works:

---

## 🏗️ 1. The Blueprint (The Identity)
Before the factory starts, it needs to know what it is making and for whom.
- **The Files:** `.env` and `src/config.py`
- **What they do:** These files hold the "Rules" of your brand. They tell the factory: "Our name is X, we are in the Y industry, and we want to target customers in City Z." 
- **In Simple Terms:** This is the factory's **ID card** and **Instruction Manual**.

## 🔍 2. The Scout (The Researcher)
The factory doesn't just guess what to write about; it looks at what is popular right now.
- **The File:** `src/scraper.py`
- **What it does:** It goes out to competitor websites, looks at their blog titles and keywords, and brings that information back.
- **In Simple Terms:** This is like a **spy** who checks what other successful shops are selling so your factory can make something even better.

## 🧠 3. The Brains (The AI Workers)
Inside the factory, there are two main "Expert Workers" (Powered by AI):
1.  **The Writer (`src/agents.py`):** Uses the research from the Scout to write a long, interesting article.
2.  **The SEO Specialist (`src/agents.py`):** This is the quality inspector. They check the article to make sure it has the right keywords so that Google will show it to people.
- **In Simple Terms:** One worker **writes the story**, and the other **checks the homework** to make sure it's perfect.

## 👔 4. The Manager (The Orchestrator)
This is the most important part. It coordinates all the workers.
- **The File:** `src/services/orchestrator.py`
- **What it does:** The Manager gives the Writer a topic, takes the draft to the SEO Specialist, and if the specialist says "This isn't good enough," the Manager sends it **back to the Writer** to fix it.
- **In Simple Terms:** This is the **Boss** who makes sure nobody slacks off and the final product is 100% ready.

## 🎨 5. The Artist (The Illustrator)
Once the article is written, it needs a beautiful cover photo.
- **The File:** `src/image_client.py`
- **What it does:** It sends the article's title to an AI (Google Gemini) and asks it to paint a professional picture.
- **In Simple Terms:** This is the **Graphic Designer** who makes the blog post look pretty.

## 📬 6. The Postman (The Publisher)
Now that the article is written, checked, and has a picture, it needs to go to the website.
- **The Files:** `src/publishers/` (WordPress, Blogger, etc.)
- **What they do:** They log into your website and "post" the article exactly where it needs to go.
- **In Simple Terms:** This is the **Delivery Driver** who takes the finished product from the factory and puts it on the store shelves.

## 📂 7. The Filing Cabinet (Storage)
The factory keeps a record of everything it has ever made.
- **The Folder:** `data/`
- **What it does:** It saves all the articles in a spreadsheet (`articles.csv`) so the factory never writes the same thing twice.
- **In Simple Terms:** This is the **Memory** of the factory.

---

### The Workflow in 5 Seconds:
1. **Identify** who we are (Config).
2. **Spy** on competitors (Scraper).
3. **Write and Check** the content (AI Agents).
4. **Paint** a picture (Image AI).
5. **Post** it to the web (Publisher).
