"""
Prompts Module
This module contains functions that generate the structured prompts
used to guide the Language Model's output for both title and content generation.
"""
import random
from typing import List, Optional, Dict

from src.config import Config

def create_title_prompt(num: int, project_context: str, article_type: str = "generic", scraped_keywords: List[str] = None, category: str = "", seed_title: str = "") -> str:
    """
    Creates a prompt for generating SEO-optimized blog titles.
    """
    is_brand_article = article_type.lower() == "brand"
    
    # Add category context if present
    category_instruction = ""
    if category:
        if is_brand_article:
            category_instruction = (
                f"- **Product Category Focus:** The title MUST be about the specific product '{category}'.\n"
                f"    - **Angle:** Focus on 'how-to-use', 'where-to-apply', 'optimal usage scenarios', and 'product-specific features'.\n"
                f"    - **Example Style:** 'The Ultimate Guide to Using {category} for [Need]', 'Top Features of {category}'."
            )
        else:
            category_instruction = (
                f"- **Industry Category Focus:** The title MUST be SPECIFICALLY about the '{category}' sector.\n"
                f"    - **Angle:** Focus on 'industrial applications', 'sector-wide benefits/drawbacks', 'proper industrial usage', and 'high-level industry trends'.\n"
                f"    - **Mandatory Term:** The title **MUST** contain the word/phrase '{category}' or a direct synonym to ensure topic clarity.\n"
                f"    - **Hierarchy:** The CATEGORY ({category}) is the MASTER TOPIC. Keywords are just modifiers.\n"
                f"- **DYNAMIC TOPICAL ISOLATION:** \n"
                f"        - The title MUST stay exclusively within the specific universe of '{category}'.\n"
                f"        - Identify the relevant industry sector and FORBID context-mixing from unrelated sectors.\n"
                f"        - If '{category}' is a technical or professional topic, do NOT mention unrelated residential or consumer contexts unless they are the target.\n"
                f"        - Ensure the title remains focused on the primary utility and value of '{category}' within its specific industry."
            )
            
    # Include scraped keywords if available (for generic articles)
    keywords_instruction = ""
    if scraped_keywords and not is_brand_article:
        # Pick 8 random keywords to ensure variety across batches
        keyword_sample = random.sample(scraped_keywords, min(len(scraped_keywords), 8))
        sample_keywords = ", ".join(keyword_sample)
        keywords_instruction = f"- **Secondary Keywords (Use ONLY as modifiers):** {sample_keywords}"

    brand_instruction = ""
    if is_brand_article:
        brand_instruction = f"""
        - **Brand Focus:** Titles MUST mention "{Config.BRAND_NAME}".
        - **Format:** Focus on high-value benefits, specific product durability, or solving maintenance problems.
        - **NO LOCATION:** Do NOT mention specific cities like "{Config.TARGET_CITY}" in the TITLE.
        """
    else:
        brand_instruction = f"""
        - **Industry Focus:** Educational, technical, and broad. 
        - **Brand Exclusion:** Do NOT mention specific brands like "{Config.BRAND_NAME}".
        - **No City:** Do NOT mention specific cities like "{Config.TARGET_CITY}".
        - **Styles:** Use "The Science of...", "Comparison", "Ultimate Guide", or "Future Trends".
        """

    seed_instruction = ""
    if seed_title:
        seed_instruction = f"- **Seed Title:** Use this as a base and REPHRASE it to be more engaging and SEO-friendly: '{seed_title}'"

    prompt = f"""
    You are an SEO expert for the {Config.INDUSTRY_NAME}. Generate {num} distinct, unique, and high-CTR blog post titles.

    **CONTEXT:**
    {project_context}
    
    **REQUIREMENTS:**
    - **LANGUAGE: MUST be in English ONLY.** Failure to comply will result in immediate rejection.
    - **Article Type:** {'Brand-Specific' if is_brand_article else 'Industry-Generic'}
    {category_instruction}
    {brand_instruction}
    {keywords_instruction}
    {seed_instruction}
    - **Length:** 40-65 characters.
    - **SEO:** Title MUST contain a relevant industry keyword naturally.
    
    - **VARIETY CHECKLIST (MANDATORY - FAILURE TO COMPLY WILL RESULT IN REJECTION):**
        1. **NO REPETITIVE STARTING WORDS:** Each title MUST start with a COMPLETELY DIFFERENT word.
            BAD EXAMPLE:
           - "How to Improve Your Workflow"
           - "How to Boost Team Productivity"
           - "How to Optimize Business Operations"
            GOOD EXAMPLE:
           - "Practical Ways to Improve Your Workflow"
           - "Boost Team Productivity with These Tools"
           - "Optimize Business Operations Effectively"
        
        2. **NO COLON OVERUSE:** Avoid repetitive "[Topic]: [Benefit]" structures.
        
        3. **LINGUISTIC DIVERSITY:** Use a mix of:
            - Action Verbs (Achieve, Protect, Enhance, Transform, Optimize)
            - Questions (How do..., What are..., Why is... necessary?)
            - Guides (Practical Handbook for..., Strategies for..., Technical Analysis of...)
            - Benefits (Sustainable Methods, Cost-Savings in..., Long-Term Performance)
            - Lists (X Essential Steps, X Key Factors, X Innovative Approaches)
        
        4. **ANGLE MIX:** Use different angles like:
            - Technical/Deep-Dive
            - Economic/ROI-focused
            - Safety & Compliance
            - Innovation/Modern Trends
            - Problem/Solution
        
        5. **FORBIDDEN PATTERNS:**
            - DO NOT start more than 10% of titles with "The".
            - DO NOT use the words "Mastering", "Unlocking", "Unveiling", "Discover", or "Ultimate" unless absolutely necessary for the tone.
            - DO NOT use repetitive "[Word]: [Phrase]" structures.
    
    - **Tone:** Professional, authoritative, and helpful.
    - **Output:** Return ONLY a numbered list.

    **OUTPUT FORMAT:**
    1. [Title 1]
    2. [Title 2]
    ...
    {num}. [Title {num}]
    
    Return ONLY the numbered list of titles. EVERY title must start with a different word.
    """
    return prompt


def create_location_sanitizer_prompt(
    sample_titles: List[str],
    sample_keywords: List[str],
    need_titles: int,
    need_keywords: int,
    allowed_localities: List[str],
) -> str:
    """Creates a prompt that forces titles/keywords to be strictly specific to the target city.

    The model is instructed to:
    - keep only {Config.TARGET_CITY} content
    - rewrite or drop anything that cannot be localized
    - output a numbered TITLES list followed by a single KEYWORDS line.
    """

    allowed = ", ".join(allowed_localities)
    sample_titles_block = "\n".join(sample_titles)
    sample_keywords_block = ", ".join(sample_keywords)
    city = Config.TARGET_CITY

    prompt = (
        f"You will SANITIZE and TOP UP {Config.INDUSTRY_NAME} blog TITLES and KEYWORDS to be strictly {city}-only.\n\n"
        f"STRICT LOCATION POLICY:\n"
        f"- All outputs must be about {city}.\n"
        f"- Treat allowed localities as {city} (allowed).\n"
        f"- If any item mentions a non-{city} city/locality (including local areas), rewrite it to '{city}' or an allowed locality.\n"
        f"- Allowed localities: [{allowed}]\n"
        f"- Any locality not in this list is forbidden; rewrite or replace.\n"
        f"- If an item cannot be localized, DROP it and create an {city}-only alternative.\n\n"
        f"NEEDS: +{need_titles} TITLES and +{need_keywords} KEYWORDS after sanitizing and deduping.\n\n"
        f"INPUT (examples):\n"
        f"Current Titles:\n{sample_titles_block}\n\n"
        f"Current Keywords:\n{sample_keywords_block}\n\n"
        f"OUTPUT FORMAT (CRITICAL — EXACTLY THIS):\n"
        f"TITLES:\n"
        f"1. <{city}-only title>\n"
        f"2. <{city}-only title>\n"
        f"...\n"
        f"KEYWORDS:\n"
        f"keyword 1, keyword 2, keyword 3, ...\n"
    )
    return prompt


def create_content_prompt(
    title: str,
    reference_text: str,
    target_keywords: List[str],
    project_context: str,
    article_type: str = "generic",
    category: str = "",
    media_assets: Optional[List[Dict]] = None,
    bucketlistt_cta_url: str = "https://www.bucketlistt.com/"
) -> str:
    """
    Creates the main, detailed prompt for generating a full blog article.
    
    Args:
        title: The initial seed title of the article
        reference_text: Previous version or reference material
        target_keywords: List of target keywords to include
        project_context: Context about the project or industry
        article_type: Type of article ('brand' or 'generic')
        category: Category of the article (Product or Industry)
    """
    # ── Client Directive: 1 + 1-2 + 2-3 keyword hierarchy ────────────────────
    # target_keywords[0]    = Main Keyword (1)
    # target_keywords[1:3]  = Secondary Keywords (1-2)
    # target_keywords[3:6]  = Additional Keywords (2-3)
    main_keyword     = target_keywords[0] if target_keywords else ""
    secondary_kws    = target_keywords[1:3] if len(target_keywords) > 1 else []
    additional_kws   = target_keywords[3:6] if len(target_keywords) > 3 else []
    keywords_str     = ", ".join(target_keywords)  # kept for legacy density checks

    # Format the keyword hierarchy block for the prompt
    secondary_str  = ", ".join(secondary_kws)  if secondary_kws  else "(none provided)"
    additional_str = ", ".join(additional_kws) if additional_kws else "(none provided)"

    keyword_hierarchy_block = f"""
    ╔══════════════════════════════════════════════════════════════════╗
    ║   KEYWORD TARGETING FRAMEWORK (CLIENT DIRECTIVE — MANDATORY)     ║
    ╚══════════════════════════════════════════════════════════════════╝

    This article MUST follow the 1 + 1-2 + 2-3 keyword hierarchy:

    ┌─ MAIN KEYWORD (×1 only) ───────────────────────────────────────┐
    │  "{main_keyword}"
    │  • Use in: H1 title, URL slug, first 50 words, image alt text
    │  • Repeat naturally throughout content (aim 2-4% density)
    │  • This keyword DRIVES the entire article topic
    └────────────────────────────────────────────────────────────────┘

    ┌─ SECONDARY KEYWORDS (1-2) ──────────────────────────────────────┐
    │  {secondary_str}
    │  • Use in: H2 subheadings and body paragraphs
    │  • Each must appear at least 2-3 times naturally
    └────────────────────────────────────────────────────────────────┘

    ┌─ ADDITIONAL KEYWORDS (2-3) ─────────────────────────────────────┐
    │  {additional_str}
    │  • Use in: H2 or H3 subheading text and body paragraphs
    │  • Each must appear at least 1-2 times
    │  • Do NOT force them — only where contextually natural
    └────────────────────────────────────────────────────────────────┘
    """

    # ── Determine article type early (needed for multiple blocks below) ────────
    is_brand_article = article_type.lower() == "brand"

    # ── Client Directive: Media Asset Injection ─────────────────────────────
    media_injection_block = ""
    if media_assets:
        media_lines = []
        for asset in media_assets[:4]:  # cap at 4 media embeds per article
            anchor  = asset.get("suggested_anchor_text", asset.get("title", "Watch on Instagram"))
            url     = asset.get("url", "")
            context = asset.get("suggested_context", "")
            platform = asset.get("platform", "")
            icon = "▶" if "youtube" in platform else "📸"
            media_lines.append(f"    {icon} [{anchor}]({url}) — {context}")
        media_block_content = "\n".join(media_lines)
        media_injection_block = f"""
    ╔══════════════════════════════════════════════════════════════════╗
    ║   SOCIAL MEDIA EMBEDS — INJECT IN BODY (CLIENT DIRECTIVE)        ║
    ╚══════════════════════════════════════════════════════════════════╝

    Embed the following media links naturally inside the BODY of the article.
    RULES:
    - NEVER place ANY of these links in the first 3 paragraphs or the intro
    - Place AFTER the 4th paragraph minimum (mid-body or conclusion sections)
    - Format as contextual anchor text: e.g. <p>Watch this <a href="URL" target="_blank" rel="noopener">real customer jump experience</a> to see what to expect.</p>
    - Max 1 YouTube embed. Max 3 Instagram embeds.
    - Only include if the link is contextually relevant at that point in the article

    APPROVED MEDIA FOR THIS ARTICLE:
{media_block_content}
    """

    # ── Client Directive: Conclusion CTA ────────────────────────────────────
    # Brand articles get a soft single CTA. Generic articles get a neutral internal link suggestion.
    if is_brand_article:
        conclusion_cta_block = f"""
    ╔══════════════════════════════════════════════════════════════════╗
    ║   CONCLUSION CTA RULES (CLIENT DIRECTIVE — BRAND ARTICLES)       ║
    ╚══════════════════════════════════════════════════════════════════╝

    The conclusion MUST always include:
    1. A 2-3 sentence summary of the article's key points and key takeaways.
    2. A single, natural booking suggestion (do NOT use pushy sales language):
       Example: "Ready to experience this for yourself? Browse and compare options on
       <a href="{bucketlistt_cta_url}" target="_blank" rel="noopener">Bucketlistt</a>."
    3. Tone: Helpful and informative, NOT promotional. Write as a knowledgeable local guide.
    """
    else:
        conclusion_cta_block = f"""
    ╔══════════════════════════════════════════════════════════════════╗
    ║   CONCLUSION RULES (CLIENT DIRECTIVE — GENERIC ARTICLES)         ║
    ╚══════════════════════════════════════════════════════════════════╝

    The conclusion MUST:
    1. Summarise 2-3 key practical takeaways from the article.
    2. Encourage the reader to plan their visit to Rishikesh.
    3. Optionally (not mandatory) include ONE natural contextual link:
       Example: "For a curated list of verified operators and packages, you can explore options on
       <a href="{bucketlistt_cta_url}" target="_blank" rel="noopener">Bucketlistt</a>."
    4. Tone: Authoritative travel guide. NOT salesy or promotional.
    """

    # ── Client Directive: Link Placement Rule ───────────────────────────────
    link_placement_block = """
    ╔══════════════════════════════════════════════════════════════════╗
    ║   LINK PLACEMENT RULES (CLIENT DIRECTIVE — MANDATORY)            ║
    ╚══════════════════════════════════════════════════════════════════╝

    ❌ DO NOT place any external or booking links in the first 3 paragraphs
    ❌ DO NOT put Bucketlistt URLs in the Introduction section
    ✅ ALL booking/CTA links go in: body paragraphs (after para 4), FAQ answers, and conclusion ONLY
    ✅ Internal links to placesinrishikesh.com content are allowed anywhere
    """

    # ── Partner Brand Context Block ──────────────────────────────────────────
    # Loaded based on article category — only injected into relevant articles
    _is_bungee_article = any(term in (category or "").lower() for term in [
        "bungee", "bungy", "jump", "comparison", "operator", "best of"
    ])
    _is_paragliding_article = "paragliding" in (category or "").lower()
    _partner_is_relevant = _is_bungee_article or _is_paragliding_article

    partner_brand_block = ""
    if _partner_is_relevant:
        # Build the approved brands list contextually
        _approved_brands = []
        if _is_bungee_article:
            _approved_brands = [
                "- Himalayan Bungy — India's highest bungee at Rishikesh (117m and 111m variants)",
                "- Splash Bungy — Rishikesh bungee operator (109m splash experience, 85m freestyle)",
                "- Maa Ganga Bungy — India's highest bungee (200m+) at Devprayag, near Rishikesh",
            ]
        elif _is_paragliding_article:
            _approved_brands = [
                "- WhyNotFly — Paragliding operator, Rishikesh (tandem flights 7-20 min, safety-rated)",
            ]
        _approved_brands_str = "\n    ".join(_approved_brands)

        partner_brand_block = f"""
    ╔══════════════════════════════════════════════════════════════════╗
    ║   PARTNER BRAND MENTIONS (CLIENT DIRECTIVE — CONDITIONAL)        ║
    ╚══════════════════════════════════════════════════════════════════╝

    This article may editorially mention the following PARTNER BRANDS by name.
    These are real, verified operators. Mentioning them builds
    Google E-E-A-T trust signals and makes the article genuinely informative.

    APPROVED PARTNER BRANDS FOR THIS ARTICLE TYPE:
    {_approved_brands_str}

    RULES FOR PARTNER BRAND MENTIONS:
    - Mention partner brands by name in body paragraphs AFTER paragraph 4
    - Mention price, height, and brief feature description (neutral, factual tone)
    - Always conclude with: "Compare and book via Bucketlistt" — linking to {bucketlistt_cta_url}
    - In comparison articles, mention ALL relevant partners for full editorial coverage

    STRICTLY FORBIDDEN:
    - NEVER mention partner brands in the Introduction (first 3 paragraphs)
    - NEVER add links to ANY third-party operator website URL (e.g. their .com domain)
    - NEVER say one operator is "better" — present each factually, let the reader decide
    - NEVER fabricate heights, prices, or features — use only the approved facts above
    - DO NOT mention Maa Ganga Bungy as a "Rishikesh" operator — it is in Devprayag

    EXAMPLE APPROVED MENTION PATTERN (bungee articles):
    "Rishikesh has several bungee operators catering to different budgets and preferences.
    Himalayan Bungy offers jumps at 117 metres and 111 metres, while Splash Bungy
    provides a unique 109-metre experience where jumpers touch the Ganga river.
    For the highest bungee in India, Maa Ganga Bungy at Devprayag offers a 200+ metre
    jump — though it requires a separate trip from Rishikesh. Compare all
    available options and book online through
    <a href="{bucketlistt_cta_url}" target="_blank" rel="noopener">Bucketlistt</a>."
    """


    # ── Client Directive: FAQ Section ───────────────────────────────────────
    faq_block = f"""
    ╔══════════════════════════════════════════════════════════════════╗
    ║   FAQ SECTION RULES (CLIENT DIRECTIVE — MANDATORY)               ║
    ╚══════════════════════════════════════════════════════════════════╝

    You MUST add a mandatory FAQ section BEFORE the conclusion.
    REQUIREMENTS:
    - MINIMUM 7 questions, aim for 8-10 for best PAA / featured snippet / AI Overview coverage.
    - FAILURE TO INCLUDE AT LEAST 7 QUESTIONS WILL RESULT IN ARTICLE REJECTION.
    - Source questions from REAL things people search on Google about "{main_keyword}":
        • Google Autocomplete (type the keyword and note the dropdown suggestions)
        • "People Also Ask" boxes at the bottom of search results
        • Long-tail keyword variations ("how to", "best time", "is it safe", "cost", "duration")
    - Each answer: 2-4 direct, factual, conversational sentences. NO filler or vague responses.
    - Write answers as a knowledgeable local guide speaking to a first-time visitor.
    - Use FAQPage schema markup format (see output structure below)
    - NEVER use <h2> inside the FAQ body — ONLY <h3> for questions, <p> for answers
    """

    # ── Client Directive: Image-First Instruction ────────────────────────────
    image_first_block = """
    ╔══════════════════════════════════════════════════════════════════╗
    ║   IMAGE PLACEMENT (CLIENT DIRECTIVE)                             ║
    ╚══════════════════════════════════════════════════════════════════╝

    The article MUST start with a featured image placeholder BEFORE the H1 title:
    <figure class="featured-image">
      <img src="[FEATURED_IMAGE_URL]" alt="[main_keyword] — descriptive alt text including the main keyword" />
      <figcaption>[Main keyword] — [short descriptive caption]</figcaption>
    </figure>

    Image alt text MUST include the Main Keyword naturally.
    """

    # ── Title Rephrasing Instruction:
    # If the seed title doesn't fit the category well, the AI can rephrase it.
    title_instruction = (
        f"The requested title is: '{title}'.\n"
        f"**ADAPTABILITY MANDATE:** If this title does not naturally fit the assigned category ({category}), "
        "you MUST rephrase the <h1> heading to be technically accurate and relevant to the category while "
        "retaining the core intent of the original title."
    )
    
    # Add category context to the prompt
    category_context = ""
    if category:
        if is_brand_article:
            category_context = (
                f"\n- **Product Category Focus:** This article focuses on the specific product **{category}**. "
                f"Naturally mention {category} throughout. The content SHOULD focus on: "
                f"Practical 'how-to' guides, optimal usage for DIY or professional projects, safety tips for application, "
                f"and unique features of the product."
            )
        else:
            category_context = (
                f"\n- **Industry Category Focus:** The entire article MUST be about the **{category}** industry sector. "
                f"Every section should discuss industrial applications, large-scale usage scenarios, "
                f"sector-wide benefits and drawbacks, technical industrial standards, and professional best practices. "
                f"Avoid focusing solely on a single product; keep it broad and authoritative about the whole {category} field."
            )
    
    # Set up brand-specific content if needed
    brand_specific_content = ""
    if is_brand_article:
        brand_specific_content = f"""
        - **Brand Tone:** Write as a knowledgeable local expert who happens to recommend {Config.BRAND_NAME} based on genuine experience. NOT as a salesperson.
        - **Brand Mentions:** Mention "{Config.BRAND_NAME}" naturally 4-6 times MAXIMUM. More than 6 mentions feels promotional and hurts credibility.
        - **Brand Voice:** Warm, helpful, and authoritative. Prioritise being useful to the reader over promoting the brand.{category_context}
        - **Soft CTA:** One natural mention of booking/comparing via {Config.BRAND_NAME} — in the body and/or conclusion. NO hard sells.
        """
    
    # Set up industry-specific content
    industry_specific_content = f"""
    - **Primary Focus:** Write a PRACTICAL, USEFUL travel guide for someone planning to visit Rishikesh. Every section should answer real questions a traveller would ask.{category_context}
    - **Writing Style:** First-person knowledgeable travel guide voice. Think: experienced traveller sharing hard-won advice, not a corporate content writer.
    - **Practical Content:** Include SPECIFIC details — best time of day/year to visit, what to wear, how to get there, approximate costs, safety tips, insider tips locals don't tell tourists.
    - **Brand Neutral:** Do NOT mention {Config.BRAND_NAME} or any single booking platform by name in the article body. One optional soft mention in the conclusion only.
    - **Category vs Keywords:** The TOPIC is {category}. The KEYWORDS are just ingredients. Use keywords where natural; never force them or change the core topic.
    - **Local Authority:** Include at least one specific local detail that demonstrates real knowledge of Rishikesh (e.g. specific ghat names, local landmark, typical prices in INR, seasonal nuance).
    """
    
    # Set up the main content requirements
    content_requirements = f"""
    **META DATA REQUIREMENTS:**
    - **META_TITLE:** 50-65 characters, include primary keyword.
    - **META_DESCRIPTION:** 120-155 characters (CRITICAL: Do NOT wrap in quotes, do NOT exceed 155 characters, and make sure it has at least 120 characters), compelling summary that includes 1-2 keywords.
        - **UNIQUENESS RULE:** MUST be an engaging "hook" or "curiosity gap".
        - **FORBIDDEN starters:** "Introduction to", "Welcome to", "In this article", "Discover how", "Looking for", "Explore our".
        - **MANDATORY:** Start with a bold claim, a surprising fact, or a direct solution-oriented statement.
    - **URL_SLUG:** hyphenated lowercase version of the title.
    - **FOCUS_KEYWORD:** The primary keyword for the article (1-3 words).
    
    **CONTENT REQUIREMENTS:**
    - **Word Count:** MANDATORY minimum 1100 words. Expand every section with extreme depth and professional expertise.
    - **SEO Score Target:** Achieve 100/100 optimization.
    - **Keyword Density:** Maintain a strict density of 2.5% to 5.0% for the provided keywords. Mention each keyword at least 3-5 times in the content. Avoid repetitive sentences.
    - **Factual Accuracy:** Ensure all information is accurate and up-to-date (2026 data).
    {brand_specific_content if is_brand_article else industry_specific_content}
    """
    
    # Set up the content structure based on article type
    if is_brand_article:
        content_structure = f"""
        **CONTENT STRUCTURE FOR BRAND-SPECIFIC ARTICLE:**
        Write this as a helpful travel activity guide that features {Config.BRAND_NAME} as the recommended provider — NOT as a promotional brochure.

        1.  **ENGAGING INTRODUCTION (200-250 words):**
            - FORBIDDEN opening patterns: "In the world of...", "When it comes to...", "Have you ever...", "In today's...", "{Config.BRAND_NAME} offers...", "Are you looking for..."
            - START with a vivid, specific scene or surprising fact about the activity/experience in {Config.TARGET_CITY}.
            - Example: "The moment the zip-line harness clicks into place above the Ganges gorge, every fear transforms into exhilaration."
            - Mention {Config.BRAND_NAME} ONCE in the intro — as a natural reference ("operators like {Config.BRAND_NAME}"), NOT as the main subject.
            - Include the primary keyword within the first 50 words.

        2.  **MAIN SECTION 1 - Complete Activity Guide (400-500 words):**
            - H2 heading: Practical guide to doing this activity in {Config.TARGET_CITY}.
            - Cover: what to expect, how to prepare, what to wear/bring, physical requirements, safety basics.
            - Use at least two H3 sub-sections (e.g. "What to Expect on the Day", "Safety Tips and Requirements").
            - This section should be 80% practical info, 20% mentions of {Config.BRAND_NAME} as a recommended option.

        3.  **MAIN SECTION 2 - Planning Your Experience (400-500 words):**
            - H2 heading: Planning and logistics (best time, how to get there, costs, booking tips).
            - Include: approximate costs in INR, best season/time of day, how to reach the location, what's included.
            - Mention {Config.BRAND_NAME}'s specific offerings (pricing, inclusions) as part of the practical comparison — NOT as advertisement.
            - Use at least two H3 sub-sections.

        4.  **MAIN SECTION 3 - Local Tips & Insider Knowledge (300-400 words):**
            - H2 heading: Insider tips and local knowledge for the best experience.
            - Share genuine local knowledge: best photo spots, what to avoid, nearby spots to combine with this activity.
            - Reference {Config.BRAND_NAME} naturally if relevant (e.g. "{Config.BRAND_NAME} provides guides who know the best spots").

        5.  **PRACTICAL CONCLUSION (150-200 words):**
            - FORBIDDEN: "In conclusion...", "To sum up...", "In summary..."
            - END with actionable next steps: when to book, what to do first, encouragement to take the leap.
            - One natural booking mention: "You can compare operators and book your slot on {Config.BRAND_NAME}."
            - Tone: encouraging and helpful, like advice from a friend who has done this many times.
        """
    else:
        content_structure = f"""
        **CONTENT STRUCTURE FOR GENERIC RISHIKESH TRAVEL GUIDE ARTICLE:**
        Write this as a PRACTICAL, USEFUL guide for someone planning to visit Rishikesh. Every section must answer real questions a first-time or repeat traveller would have.

        1.  **ENGAGING INTRODUCTION (200-250 words):**
            - FORBIDDEN: "In the world of...", "When it comes to...", "In today's...", "Introduction to...", "In this blog post..."
            - START with a vivid, specific detail that puts the reader in Rishikesh right now:
              e.g. "The sound of the Ganges changes after dark..." or "Most travellers don't realise that {Config.TARGET_CITY} has two completely different personalities..."
            - Hook from personal or local knowledge — NOT from generic statistics.
            - State clearly what practical questions this article will answer.
            - Include the primary keyword within the first 50 words.

        2.  **MAIN SECTION 1 — What It Is & Why You Should Care (350-450 words):**
            - H2: Explain the specific experience/activity/topic and why it matters for a Rishikesh trip.
            - Be concrete: where exactly, what it involves, who it is right for.
            - Use two H3 sub-sections (e.g. "What to Expect" and "Who Is It Best For").
            - Include at least one specific local detail: a ghat name, a landmark, a local price in INR.

        3.  **MAIN SECTION 2 — How To Do It: Practical Step-by-Step Guide (400-500 words):**
            - H2: The practical HOW-TO section. This is the heart of the article.
            - Cover: preparation, booking, what to wear/bring, getting there, what happens on the day.
            - Use a numbered list OR bullet checklist for at least part of this section.
            - Include: typical costs (INR), time required, physical requirements, safety notes.
            - Use two H3 sub-sections.

        4.  **MAIN SECTION 3 — Insider Tips & Best Practices (300-400 words):**
            - H2: Insider knowledge that separates experienced travellers from tourists.
            - Share: best time of year, best time of day, what to avoid, nearby spots to combine.
            - At least one genuinely local tip that is NOT in every other travel blog.
            - Optional: seasonal variation (monsoon vs winter vs summer experience differences).

        5.  **PRACTICAL CONCLUSION (150-200 words):**
            - FORBIDDEN: "In conclusion...", "To sum up...", "In summary..."
            - END with clear, actionable next steps: when to book, what to do first, one key reminder.
            - Tone: like a well-travelled friend giving their honest final recommendation.
            - One optional soft link to a booking platform — only if naturally fits the content.
        """
    
    # Set up the SEO requirements with STRICT HTML FORMAT
    seo_requirements = """
    ╔══════════════════════════════════════════════════════════════════════════════╗
    ║  ABSOLUTE STRICT HTML FORMAT - MUST FOLLOW EXACTLY OR ARTICLE WILL BE REJECTED  ║
    ╚══════════════════════════════════════════════════════════════════════════════╝
    
    You are an **expert HTML developer** who has written thousands of perfectly formatted HTML documents.
    Write this article as if you are coding a production-ready HTML page. Every tag must be syntactically perfect.
    
    **STRICT HTML SYNTAX:** All HTML tags MUST be perfectly formatted.
        - NO Markdown: NEVER use `**` for bolding. Use `<strong>` or `<b>` only.
        - NO Naked Tags: Tag names (like h3, p, li) must NEVER appear as plain text. 
        - Tags MUST be wrapped in brackets (e.g., `<h3>`, NOT `h33` or `h3.`).
        - Every tag MUST have BOTH opening `<` and closing `>` brackets.
    
    ### HEADING HIERARCHY (MANDATORY - NO EXCEPTIONS):
    | Tag   | Usage                                      | Count  |
    |-------|-------------------------------------------|--------|
    | <h1>  | ONLY the main article title               | 1      |
    | <h2>  | Main sections (intro, body sections, FAQ) | 4-5    |
    | <h3>  | Subsections and FAQ questions             | 6-10   |
    | <h4>  | FORBIDDEN - NEVER USE                     | 0      |
    | <h5>  | FORBIDDEN - NEVER USE                     | 0      |
    | <h6>  | FORBIDDEN - NEVER USE                     | 0      |
    
    ### ABSOLUTE TAG SYNTAX RULES (ZERO TOLERANCE FOR ERRORS):
    
    1. **ZERO SPACES IN TAGS:**
       ✅ CORRECT: <b>text</b>    <p>content</p>    <h2>heading</h2>
       ❌ WRONG:   < b>text< /b>  < p>content< /p>  <h2 >heading</h2 >
       ❌ WRONG:   <b >text</b >  <p >content</p >  < h2>heading< /h2>
    
    2. **ALWAYS CLOSE TAGS IMMEDIATELY:**
       ✅ CORRECT: <b>important word</b> rest of sentence
       ❌ WRONG:   <b>important word rest of sentence</b> (closing too late)
       ❌ WRONG:   <b>important word (never closed)
    
    3. **NO NAKED TAG NAMES:**
       ✅ CORRECT: <h3>What Are The Benefits?</h3>
       ❌ WRONG:   h3 What Are The Benefits? h3
       ❌ WRONG:   h 3 What Are The Benefits? h4
       ❌ WRONG:   <h3 What Are The Benefits?
    
    4. **PROPER BOLD/STRONG USAGE (CRITICAL - MOST COMMON ERROR):**
       
        RULE: Only bold SHORT PHRASES (1-5 words MAX). NEVER bold entire sentences or paragraphs!
        RULE: Close the </b> tag IMMEDIATELY after the emphasized word(s)!
       
       ✅ CORRECT EXAMPLES:
          - "We offer <b>premium quality</b> solutions for your business."
          - "Our <b>expert team</b> provides <b>reliable support</b> for all projects."
          - "Choose <b>{Config.BRAND_NAME}</b> for the best results."
       
       ❌ WRONG - ENTIRE SENTENCE BOLDED (WILL BE REJECTED):
          - "<b>We take pride in serving this community by offering reliable solutions catered specifically towards regional needs.</b>"
       
       ❌ WRONG - TAG NOT CLOSED IMMEDIATELY:
          - "<b>We take pride in serving this community</b> by offering reliable solutions" (Too many words bolded)
          - "We offer <b>premium quality solutions for your business and all your needs</b>" (More than 5 words)
       
       ❌ WRONG - MARKDOWN SYNTAX:
          - "Use **bold text** for emphasis." (NO MARKDOWN - use <b>)
       
       ❌ WRONG - SPACES IN TAGS:
          - "Use < b>bold text< /b> for emphasis." (NO SPACES IN TAGS)
       
       📋 SELF-CHECK FOR EVERY <b> TAG:
          □ Is only 1-5 words inside the <b>...</b>?
          □ Is </b> immediately after the emphasized word(s)?
          □ Are there NO spaces in < b> or < /b>?
    
    5. **PARAGRAPH STRUCTURE:**
       ✅ CORRECT: <p>This is a complete paragraph with proper closing.</p>
       ❌ WRONG:   <p>This is a paragraph <p>New paragraph starts (missing close)
       ❌ WRONG:   < p>Paragraph with spaces< /p>
    
    6. **LIST FORMATTING:**
       ✅ CORRECT:
       <ul>
           <li>First item</li>
           <li>Second item</li>
       </ul>
       ❌ WRONG:
       <ul>
           <li>First item
           <li>Second item (missing </li> tags)
       </ul>
    
    7. **COMPLETE TAG BRACKETS (CRITICAL - MOST COMMON ERROR):**
       Every HTML tag MUST have BOTH angle brackets: opening < and closing >
       
       ✅ CORRECT OPENING TAGS:
          <h1>  <h2>  <h3>  <p>  <b>  <ul>  <li>  <strong>  <blockquote>
       
       ✅ CORRECT CLOSING TAGS:
          </h1>  </h2>  </h3>  </p>  </b>  </ul>  </li>  </strong>  </blockquote>
       
       ❌ INCOMPLETE/TRUNCATED TAGS (IMMEDIATE REJECTION):
          <h3   (missing closing >)
          <h2   (missing closing >)
          <p    (missing closing >)
          <b    (missing closing >)
          h3>   (missing opening <)
          /h3>  (missing opening <)
       
       ❌ REAL EXAMPLES OF FAILURES:
          "<h3What Are The Benefits?" → WRONG (missing > after h3)
          "<h3 What Are The Benefits?" → WRONG (space before >, should be <h3>What...)
          "< h3>Question</h3>" → WRONG (space after <)
       
       ✅ THE ONLY CORRECT WAY:
          "<h3>What Are The Benefits?</h3>" → CORRECT
    
    8. **MANDATORY TAG PAIRING (EVERY OPEN TAG MUST BE CLOSED):**
       
       CRITICAL: EVERY opening tag MUST have a corresponding closing tag! 🚨🚨🚨
       
       FOR EVERY <strong> YOU WRITE, YOU MUST WRITE </strong>:
       ✅ CORRECT: "We provide <strong>quality</strong> services."
       ❌ WRONG:   "We provide <strong>quality services." (MISSING </strong> - CAUSES ALL TEXT TO BE BOLD)
       
       FOR EVERY <b> YOU WRITE, YOU MUST WRITE </b>:
       ✅ CORRECT: "Our <b>expert team</b> is here to help."
       ❌ WRONG:   "Our <b>expert team is here to help." (MISSING </b> - CAUSES ALL TEXT TO BE BOLD)
       
       FOR EVERY <h3> YOU WRITE, YOU MUST WRITE </h3>:
       ✅ CORRECT: "<h3>What Are The Benefits?</h3>"
       ❌ WRONG:   "<h3>What Are The Benefits?" (MISSING </h3> - CAUSES CONTENT LOSS)
       ❌ WRONG:   "<h3 What Are The Benefits?" (MISSING > - CAUSES CONTENT LOSS)
       
       TAG PAIRING VERIFICATION:
          Before writing ANY emphasis tag, plan the sentence:
          1. Write opening tag: <strong>
          2. Write 1-5 words to emphasize
          3. IMMEDIATELY write closing tag: </strong>
          4. Continue with rest of sentence
       
       FAILURE TO CLOSE TAGS WILL CAUSE:
          - Entire paragraphs appearing in bold
          - Missing content on the website
          - Broken HTML structure
          - IMMEDIATE ARTICLE REJECTION
    
    ### CONTENT REQUIREMENTS:
    - Use at least 15-20 <p> paragraphs across the article.
    - Include at least two <ul> or <ol> lists with multiple <li> items.
    - Use <b> or <strong> to emphasize key phrases at least 10 times.
    - Use <blockquote> for at least one expert tip or important note.
    - Keyword density: 1.5% to 3.0% without keyword stuffing.
    
    ### BEFORE SUBMITTING - MANDATORY SELF-CHECK:
    □ Every opening tag has BOTH brackets: <tag> NOT <tag or tag>
    □ Every closing tag has BOTH brackets: </tag> NOT </tag or /tag>
    □ Every <b> tag has a matching </b> (no spaces: NOT < /b>)
    □ Every <strong> tag has a matching </strong> (CRITICAL - unclosed causes bold overflow)
    □ Every <p> tag has a matching </p> (no spaces: NOT < /p>)
    □ Every <h2> tag has a matching </h2> (no spaces: NOT < /h2>)
    □ Every <h3> tag has a matching </h3> (no spaces: NOT < /h3>)
    □ Every <li> tag has a matching </li> (no spaces: NOT < /li>)
    □ NO incomplete tags like <h3 or <p or <b or <strong (MUST have closing >)
    □ COUNT your <strong> tags and </strong> tags - THEY MUST BE EQUAL
    □ COUNT your <b> tags and </b> tags - THEY MUST BE EQUAL
    □ NO h4, h5, or h6 tags anywhere in the document
    □ NO Markdown syntax (**bold**, - bullets, etc.)
    □ NO spaces inside any HTML tags
    """
    
    # Add brand-specific SEO requirements if needed
    if is_brand_article:
        seo_requirements += f"""
        - Mention "{Config.BRAND_NAME}" naturally 4-6 times MAXIMUM. Excessive mentions feel promotional and harm reader trust.
        - **LOCAL SEO:** Weave "{Config.TARGET_CITY}" into the narrative naturally. Aim for 4-6 mentions.
        - **NATURAL PHRASES:** Use location phrases like "in {Config.TARGET_CITY}", "near the Ganges", "in the Himalayas" only where they add genuine context.
        - The article must read like a helpful travel guide written by a local expert — NOT like a sales page.
        """
    else:
        seo_requirements += f"""
        - **BRAND NEUTRALITY:** You are writing as an independent travel expert. Do NOT mention "{Config.BRAND_NAME}" in the article body.
        - **LOCAL RELEVANCE:** Naturally weave "{Config.TARGET_CITY}" and "{Config.TARGET_STATE}" into the narrative (aim for 5-7 natural mentions).
        - **Objective Authority:** Write from direct experience and knowledge. Specific, practical details build more trust than broad claims.
        - **Reader First:** Every sentence should answer a question or solve a problem for someone planning a Rishikesh trip.
        """
    
    # Detect if this is a revision based on feedback
    revision_instruction = ""
    if "PREVIOUS SEO REPORT" in reference_text or "previous attempt scored" in reference_text.lower():
        revision_instruction = f"""
    > [!IMPORTANT]
    > **CRITICAL REVISION INSTRUCTIONS:**
    > Your previous draft FAILED to meet the SEO criteria. You MUST prioritize fixing the specific issues listed below.
    > 
    > **FAILURES TO ADDRESS:**
    > 1. Look closely at the "Previous attempt scored..." feedback in the revision materials.
    > 2. WORD COUNT: If it was low, you MUST double the length of your H3 sections. Add more examples and professional advice.
    > 3. KEYWORDS: If missing, ensuring each keyword from the list is mentioned at least 3 times.
    > 4. STRUCTURE: Ensure strict adherence to 1 H1, 4+ H2s, and 6+ H3s.
    >
    > DO NOT just regenerate the same content. ACTIVE EXPANSION and CORRECTION is required.
    """

    # Create the final prompt
    prompt = f"""
    You are a professional SEO content writer for the {Config.INDUSTRY_NAME}. Your goal is to write a comprehensive, long-form blog article that achieves a 100/100 SEO score.
    
    ### [STRICT SEO COMPLIANCE COMMANDS - READ CAREFULLY]
    | Metric | Requirement |
    | :--- | :--- |
    | **Keyword Usage** | Use keywords naturally. If a keyword conflicts with category, use it in a comparison. |
    | **Keyword Density** | Overall primary keyword density must be between 2.0% - 6.0%. |
    | **Word Count** | MINIMUM 1100 words. (Expand on details, provide examples, explain 'why' and 'how'). |
    | **Title SEO** | Title MUST include at least one Primary Keyword. |
    | **Location Density** | **STRICT MENTION COUNT LIMIT:** You MUST mention '{Config.TARGET_CITY}' exactly between 4 and 8 times TOTAL in the entire article. DO NOT exceed 9 mentions or write it less than 4 times. |
    | **Location Booster** | **STRICT BOOSTER MENTIONS (MANDATORY):** You MUST include at least 4 of these exact phrases (case-insensitive) exactly once each: 'in {Config.TARGET_CITY}', 'across {Config.TARGET_CITY}', 'top-rated in {Config.TARGET_CITY}', 'services in {Config.TARGET_CITY}', 'experts in {Config.TARGET_CITY}', 'best quality in {Config.TARGET_CITY}', 'customers in {Config.TARGET_CITY}', 'projects in {Config.TARGET_CITY}'. Weave them in naturally (e.g. "rafting experts in {Config.TARGET_CITY}"). |
    | **Structure** | 1 H1, at least 4 H2s, at least 2 H3s under EVERY H2. |
    | **Meta Data** | Meta Title: 50-65 chars. Meta Desc: 120-155 chars (CRITICAL: Do NOT wrap in quotes, strictly under 156 chars). |
    | **LANGUAGE** | **MUST be in English ONLY.** |

    {revision_instruction}

    {content_requirements}

    **ARTICLE SPECIFICATIONS:**
    - **Title:** {title}
    - **Main Keyword (H1 + URL slug + alt text):** {main_keyword}
    - **Secondary Keywords (H2 + body):** {secondary_str}
    - **Additional Keywords (H2/H3):** {additional_str}
    - **Article Type:** {'Brand-Specific' if is_brand_article else 'Industry-Generic'}
    {f"- **Category:** {category}" if category else ""}
    - **CONTEXT:** {project_context}

    {keyword_hierarchy_block}

    {image_first_block}

    {link_placement_block}

    {partner_brand_block}

    {media_injection_block}

    {faq_block}

    {conclusion_cta_block}
    
    {title_instruction}
    
    {content_structure}
    
    {seo_requirements}
    
    **REVISION MATERIALS (for reference only):**
    === BEGIN REVISION MATERIALS ===
    {reference_text}
    === END REVISION MATERIALS ===

    ╔══════════════════════════════════════════════════════════════════════════════════════════════════╗
    ║   IMMEDIATE REJECTION CRITERIA - ANY OF THESE = AUTOMATIC FAILURE                               ║
    ╚══════════════════════════════════════════════════════════════════════════════════════════════════╝
    
    Your article will be IMMEDIATELY REJECTED if ANY of these occur:
    
    ❌ SPACES IN HTML TAGS (MOST COMMON FAILURE):
       - "< /b>" instead of "</b>" → REJECTED
       - "< p>" instead of "<p>" → REJECTED
       - "</h3 >" instead of "</h3>" → REJECTED
       - "<b >" instead of "<b>" → REJECTED
    
    ❌ UNCLOSED OR IMPROPERLY CLOSED TAGS:
       - "<b>word without closing tag" → REJECTED
       - "<p>paragraph <p>new paragraph" (missing </p>) → REJECTED
    
    ❌ INCOMPLETE/TRUNCATED TAGS (MISSING ANGLE BRACKETS):
       - "<h3 without closing >" → REJECTED (must be <h3>)
       - "<h2 " → REJECTED (must be <h2>)
       - "<p " → REJECTED (must be <p>)
       - "<b without >" → REJECTED (must be <b>)
       - "h3>" → REJECTED (missing opening <)
    
    ❌ NAKED TAG NAMES (NOT WRAPPED IN <>):
       - "h4 What are the benefits?" → REJECTED
       - "h 4 Question text h4" → REJECTED
       - "p This is a paragraph p" → REJECTED
    
    ❌ FORBIDDEN TAGS:
       - ANY <h4>, <h5>, or <h6> tags → REJECTED
    
    ❌ MARKDOWN SYNTAX:
       - "**bold text**" → REJECTED (use <b>bold text</b>)
       - "- bullet point" → REJECTED (use <li>)
    
    ❌ OTHER FAILURES:
       - Less than 1100 words → REJECTED
       - Any language other than English → REJECTED
       - Missing Primary Keywords (< 3 mentions each) → REJECTED
       - (Brand Only) Missing '{Config.TARGET_CITY}' (< 5 mentions) → REJECTED
       - (Generic Only) Missing '{Config.TARGET_CITY}' in article about Rishikesh travel → REJECTED
       - (Brand Only) No Bucketlistt reference anywhere in the article → REJECTED
       - NOTE: Generic articles do NOT need a hard Bucketlistt CTA. One soft link in conclusion is optional.

    ╔══════════════════════════════════════════════════════════════════════════════════════════════════╗
    ╔══════════════════════════════════════════════════════════════════════════════════════════════════╗
    ║   EXACT OUTPUT FORMAT - COPY THIS STRUCTURE PRECISELY                                           ║
    ╚══════════════════════════════════════════════════════════════════════════════════════════════════╝
    
    META_TITLE: [50-65 chars, include keyword]
    META_DESCRIPTION: [140-160 chars, mention problem & solution]
    URL_SLUG: [keyword-optimized-slug]
    FOCUS_KEYWORD: [primary keyword]
    
    <h1>[YOUR ADAPTED OR ORIGINAL TITLE HERE]</h1>
    
    [Write the long-form article here. Use professional HTML tags <h2>, <h3>, <p>, <ul>, <li>, <strong>, <b>, <blockquote>]
    [For Brand articles, naturally weave the city {Config.TARGET_CITY} into descriptions of service quality.]
    [Ensure EVERY tag is complete with both < and > brackets - NO incomplete tags like <h3 or <p]
    
    <h2>Introduction Section Title</h2>
    <p>Introductory paragraph with <b>bold emphasis</b> on key terms.</p>
    
    <h2>Main Section 1</h2>
    <p>Content paragraph.</p>
    <h3>Subsection 1.1</h3>
    <p>Detailed content with <strong>important points</strong> highlighted.</p>
    <h3>Subsection 1.2</h3>
    <p>More detailed content.</p>
    
    <h2>Main Section 2</h2>
    <p>Content paragraph.</p>
    <h3>Subsection 2.1</h3>
    <p>Content here.</p>
    <ul>
        <li>List item one</li>
        <li>List item two</li>
    </ul>
    
    [Continue with more sections following this pattern...]
    
    [DO NOT include any FAQ content above this line. The FAQ section appears ONLY after the FAQ_SECTION: marker below.]
    [The main article content ENDS here. Everything below is the separate FAQ section.]

    FAQ_SECTION:
    <div class="faq-section" itemscope itemtype="https://schema.org/FAQPage">
    <h2>Frequently Asked Questions about [Main Keyword Topic]</h2>
    [MANDATORY: 5-10 questions. Source from Google Autocomplete + PAA boxes for the main keyword.]
    [CRITICAL: ONLY <h3> for questions, <p> for answers. NO <h2>, <h4>, <h5>, NO bullet points inside FAQ.]
    [Each answer: 2-4 sentences, direct and factual. Include main/secondary keyword where natural.]
    [You MAY include 1 relevant Bucketlistt booking link inside a FAQ answer — e.g. "You can book through <a href='URL'>Bucketlistt</a>".]

    <div itemscope itemprop="mainEntity" itemtype="https://schema.org/Question">
    <h3 itemprop="name">Question 1?</h3>
    <div itemscope itemprop="acceptedAnswer" itemtype="https://schema.org/Answer">
    <p itemprop="text">Answer to question 1. (2-4 sentences)</p>
    </div>
    </div>

    <div itemscope itemprop="mainEntity" itemtype="https://schema.org/Question">
    <h3 itemprop="name">Question 2?</h3>
    <div itemscope itemprop="acceptedAnswer" itemtype="https://schema.org/Answer">
    <p itemprop="text">Answer to question 2. (2-4 sentences)</p>
    </div>
    </div>

    [Continue with 5-10 total FAQs in this exact schema format]
    </div>
    
    ### [!CONTENT END]
    
    FINAL VERIFICATION BEFORE SUBMITTING:
    ✓ Count every <b> and </b> - they MUST match (no spaces like < /b>)
    ✓ Count every <p> and </p> - they MUST match (no spaces like < /p>)
    ✓ Count every <h2> and </h2> - they MUST match
    ✓ Count every <h3> and </h3> - they MUST match
    ✓ EVERY tag has BOTH angle brackets (< and >) - NO incomplete tags like <h3 or <p
    ✓ ZERO instances of <h4>, <h5>, or <h6>
    ✓ ZERO Markdown syntax (**bold**, -, etc.)
    ✓ ZERO spaces inside angle brackets
    """
    return prompt
    
def create_keyword_extraction_prompt(text_chunk: str, num_keywords: int) -> str:
    """
    Creates a prompt for extracting high-value SEO keywords from a raw text chunk.
    """
    return f"""
    You are an expert SEO Strategist for {Config.INDUSTRY_NAME}. 
    Analyze the following text scraped from a competitor's blog post and extract the top {num_keywords} most valuable SEO keywords.

    **CRITERIA:**
    1. **Relevance:** Must be highly relevant to the {Config.INDUSTRY_NAME} and the content provided.
    2. **Specificity:** Prefer specific phrases over generic single words.
    3. **Value:** Focus on keywords that would drive qualified traffic.
    4. **Language:** Output must be in English ONLY.
    5. **Format:** Return ONLY a comma-separated list of keywords. No numbering, no bullets, no introduction.

    **TEXT TO ANALYZE:**
    {text_chunk[:3000]}  # Truncate to avoid excessive token usage if very long

    **OUTPUT:**
    """

def create_keyword_generation_prompt(text_chunk: str, num_keywords: int) -> str:
    """
    Creates a prompt to GENERATE missing keywords based on the article's topic if extraction was insufficient.
    """
    return f"""
    You are an expert SEO Strategist for {Config.INDUSTRY_NAME}.
    The following text is a blog article. We extracted some keywords, but found too few.
    
    **TASK:**
    Generate {num_keywords} *additional* high-value SEO keywords that are highly relevant to this article's topic and the {Config.INDUSTRY_NAME}.

    **CRITERIA:**
    1. **Relevance:** Must fit the article's theme.
    2. **Specificity:** Use long-tail keywords where possible.
    3. **Value:** Commercial or informational intent.
    4. **Language:** Output must be in English ONLY.
    5. **Format:** Return ONLY a comma-separated list.

    **ARTICLE CONTENT (Snippet):**
    {text_chunk[:2000]}

    **OUTPUT:**
    """

def create_raw_content_prompt(title: str, reference_text: str, target_keywords: List[str], project_context: str, article_type: str = "generic", category: str = "") -> str:
    """
    Creates a prompt for generating raw article content without HTML formatting.
    This is Step 1 of the two-step article generation process - uses temperature from .env
    """
    # Implementation will generate plain text with structure markers
    # This is a simplified placeholder - full implementation follows the plan
    from prompts.prompts import create_content_prompt
    # For now, modify the existing prompt to output plain text
    base_prompt = create_content_prompt(title, reference_text, target_keywords, project_context, article_type, category)
    # Replace HTML instructions with plain text instructions
    return base_prompt.replace("HTML", "PLAIN TEXT")

def create_html_conversion_prompt(raw_content: str, article_type: str = "generic") -> str:
    """
    Creates a prompt for converting raw content to HTML.
    This is Step 2 - uses FIXED 0.1 temperature
    """
    return f"""Convert the following plain text article to properly formatted HTML.
Use <h1>, <h2>, <h3>, <p>, <ul>, <li>, <b>, <strong> tags appropriately.
NO spaces in tags. Every tag must be properly closed.

{raw_content}
"""


def create_linkedin_prompt(title: str, content_html: str, keywords: List[str]) -> str:
    """
    Creates a prompt for generating an engaging, value-packed long-form LinkedIn article/post.
    """
    kws_str = ", ".join(keywords) if keywords else ""
    return f"""
You are an expert travel marketer and elite professional copywriter.
Generate a highly engaging, professional, long-form LinkedIn article (post commentary) based on the following article details:

**Title:** {title}
**Target Keywords:** {kws_str}
**Article Body (HTML/text):**
{content_html[:5000]}

### STRICT LinkedIn ARTICLE GUIDELINES (MANDATORY):
1. **Long-Form, Article-Like Structure**:
   - Do NOT write a brief 2-paragraph update. Write a comprehensive, value-rich LinkedIn article.
   - Use sections divided by empty lines and bullet points to make it read like a premium article.
   - Use engaging travel/professional emojis (🏔️, 📌, 🚀, 💡, 🛡️, 🌊) naturally.
   - Avoid salesy or pushy language. Write as an authoritative local guide offering genuine value.
2. **First 140 Characters Strategic Hook (CRITICAL)**:
   - The first 140 characters of the post MUST contain an exceptionally powerful hook (a bold claim, unique local insight, or engaging question).
   - This ensures the text looks spectacular in the user feed before it gets truncated by the "See more" button.
3. **Structured Body Sections**:
   - **Introduction**: Hook the reader and present a central theme.
   - **Key Actionable Takeaways**: 3-4 bullet points outlining actual, practical details (e.g. costs, best times, secret tips) from the article. ELABORATE on each point with 2-3 detailed sentences. Do not write short 1-line bullet points.
   - **Local Travel Insight**: Provide rich travel context, local atmosphere, safety guidelines, and professional tips.
4. **Length and Character Constraints (ABSOLUTE)**:
   - The entire commentary MUST be between 1,800 and 2,500 characters in length.
   - To achieve this exact range, target these specific section lengths:
     * **Introduction**: Write 2 substantial paragraphs (about 400-500 characters total) establishing the hook and local atmosphere.
     * **Key Actionable Takeaways**: Write exactly 3 detailed bullet points. For each bullet point, write exactly 2-3 detailed sentences (about 250-300 characters per bullet point, totaling ~800-900 characters).
     * **Local Travel Insight**: Write a solid paragraph of 3-4 sentences (about 400-500 characters) detailing professional tips, safety, and cultural expectations.
     * **Hashtags and Call to Action**: About 150 characters at the bottom.
   - Ensure the total character count is strictly between 1,800 and 2,400 characters. It MUST NOT exceed 2,500 characters under any circumstances so it fits within LinkedIn's 3,000 post limit.
5. **No HTML Tags**:
   - The output must be clean plain text formatted with spacing and emojis. DO NOT include any HTML tags like <b> or <p>.
6. **Hashtags and CTA**:
   - Append 4-5 relevant hashtags at the bottom (e.g., #Rishikesh, #AdventureTravel, #Bucketlistt).
   - End with a compelling professional call to action to read the full guide.

Return ONLY the ready-to-paste LinkedIn article text. Do not add any introductory/outro remarks or markdown code block backticks (like ```).
"""

