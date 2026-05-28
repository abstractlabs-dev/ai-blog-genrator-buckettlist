"""
Social Prompts Module
Contains prompt generation functions for social media platforms.
"""
import random
from typing import List


def create_linkedin_prompt(title: str, content_html: str, keywords: List[str]) -> str:
    """
    Creates a prompt for generating an engaging, value-packed long-form LinkedIn article/post.
    """
    kws_str = ", ".join(keywords) if keywords else ""

    # Anti-Fingerprinting Layout & Style Randomization
    angles = [
        "STORYTELLING ANGLE (Focus on opening with a vivid personal or travel story, "
        "emotional connection, and local atmosphere. Paint a picture for the reader and "
        "build a personal connection before introducing the value.)",
        "ANALYTICAL ANGLE (Focus on objective analysis, comparing options, presenting "
        "factual data/insights, safety standards, and practical planning aspects. "
        "Highly professional and educational tone.)",
        "INSIDER SECRETS ANGLE (Frame the post around 'insider secrets' or 'hidden tips' "
        "known only to local guides. Use a helpful, revelatory tone that makes the reader "
        "feel they are getting exclusive knowledge.)",
        "Q&A ANGLE (Frame the post around answering a central core question that "
        "travelers always ask. Start with the question directly and provide a "
        "comprehensive, authoritative answer.)"
    ]

    structures = [
        "NARRATIVE PARAGRAPH STRUCTURE: Write in clean, substantial paragraph blocks "
        "without using any bullet points or checklists. Emphasize high-quality narrative flow, "
        "smooth transitions, and deep contextual writing.",
        "BULLET-LIST STRUCTURE: Divide the key actionable takeaways into exactly 3-4 bullet points "
        "(using emojis like 📌 or 🌊). Each bullet point must contain 2-3 detailed sentences.",
        "NUMBERED STEPS STRUCTURE: Format the key takeaways as a numbered step-by-step checklist "
        "(e.g. 1️⃣, 2️⃣, 3️⃣). Elaborate on each step with 2-3 detailed sentences."
    ]

    selected_angle = random.choice(angles)
    selected_structure = random.choice(structures)

    return f"""
You are an expert travel marketer and elite professional copywriter.
Generate a highly engaging, professional, long-form LinkedIn article (post commentary) based on the following:

**Title:** {title}
**Target Keywords:** {kws_str}
**Article Body (HTML/text):**
{content_html[:5000]}

### STYLING AND FORMATTING INSTRUCTIONS (RANDOMIZED FOR ANTI-SPAM SAFETY):
- **Angle**: {selected_angle}
- **Structure**: {selected_structure}

### STRICT LinkedIn ARTICLE GUIDELINES (MANDATORY):
1. **Diverse Structural Layout**:
   - Follow the assigned structure precisely. Do NOT fallback to generic bullet points if narrative structure was assigned.
   - Use engaging travel/professional emojis (🏔️, 📌, 🚀, 💡, 🛡️, 🌊) naturally but sparingly.
   - Avoid salesy or pushy language. Write as an authoritative local guide offering genuine value.
2. **First 140 Characters Strategic Hook (CRITICAL)**:
   - The first 140 characters of the post MUST contain an exceptionally powerful hook based on the assigned Angle.
   - This ensures the text looks spectacular in the user feed before it gets truncated by the "See more" button.
3. **Structured Body Sections**:
   - **Introduction**: Hook the reader and present a central theme using the assigned Angle.
   - **Key Actionable Takeaways**: Elaborate on 3-4 key aspects using the assigned Structure.
     Each point must contain 2-3 detailed sentences. No short 1-line notes.
   - **Local Travel Insight**: Provide rich travel context, local atmosphere, safety guidelines, and professional tips.
4. **Length and Character Constraints (ABSOLUTE)**:
   - The entire commentary MUST be between 1,800 and 2,500 characters in length.
   - To achieve this exact range, target these specific section lengths:
     * **Introduction**: Write 2 substantial paragraphs (about 400-500 characters total)
       establishing the hook and local atmosphere.
     * **Key Actionable Takeaways**: Write exactly 3 detailed bullet points/paragraphs.
       Each must have 2-3 detailed sentences (totaling ~800-900 characters).
     * **Local Travel Insight**: Write a solid paragraph of 3-4 sentences (about 400-500 characters)
       detailing professional tips, safety, and cultural expectations.
     * **Hashtags and Call to Action**: About 150 characters at the bottom.
   - Ensure the total character count is strictly between 1,800 and 2,400 characters.
     It MUST NOT exceed 2,500 characters under any circumstances so it fits within LinkedIn's 3,000 post limit.
5. **No HTML Tags**:
   - The output must be clean plain text formatted with spacing and emojis. DO NOT include any HTML tags like <b> or <p>.
6. **No Raw Outbound Links**:
   - **DO NOT include any outbound URLs, main article links, or raw links in the generated post body.**
     All outbound links will be added programmatically by the publisher. Keep the commentary text 100% clean.
7. **Hashtags and CTA**:
   - Append 4-5 relevant hashtags at the bottom (e.g., #Rishikesh, #AdventureTravel, #Bucketlistt).

Return ONLY the ready-to-paste LinkedIn article text. Do not add any introductory/outro remarks or markdown.
"""
