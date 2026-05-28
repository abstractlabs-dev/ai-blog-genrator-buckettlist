"""
Templates Module
Stores static prompt string blocks and base templates.
"""
from src.config import Config


LINK_PLACEMENT_BLOCK = """
    ╔══════════════════════════════════════════════════════════════════╗
    ║   LINK PLACEMENT RULES (CLIENT DIRECTIVE — MANDATORY)            ║
    ╚══════════════════════════════════════════════════════════════════╝

    ❌ DO NOT place any external or booking links in the first 3 paragraphs
    ❌ DO NOT put Bucketlistt URLs in the Introduction section
    ✅ ALL booking/CTA links go in: body paragraphs (after para 4), FAQ answers, and conclusion ONLY
    ✅ Internal links to placesinrishikesh.com content are allowed anywhere
"""

IMAGE_FIRST_BLOCK = """
    ╔══════════════════════════════════════════════════════════════════╗
    ║   IMAGE PLACEMENT (CLIENT DIRECTIVE)                             ║
    ╚══════════════════════════════════════════════════════════════════╝

    The article MUST start with a featured image placeholder BEFORE the H1 title:
    <figure class="featured-image">
      <img src="[FEATURED_IMAGE_URL]" alt="[main_keyword] — alt text including primary keyword" />
      <figcaption>[Main keyword] — [short descriptive caption]</figcaption>
    </figure>

    Image alt text MUST include the Main Keyword naturally.
"""

REJECTION_CRITERIA = f"""
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
       - Less than {Config.MIN_WORD_COUNT} words → REJECTED
       - Any language other than English → REJECTED
       - Missing Primary Keywords (< 3 mentions each) → REJECTED
       - (Brand Only) Missing '{Config.TARGET_CITY}' (< 5 mentions) → REJECTED
       - (Generic Only) Missing '{Config.TARGET_CITY}' in article about Rishikesh travel → REJECTED
       - (Brand Only) No Bucketlistt reference anywhere in the article → REJECTED
       - NOTE: Generic articles do NOT need a hard Bucketlistt CTA. One soft link in conclusion is optional.
"""

EXACT_OUTPUT_FORMAT = f"""
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
    [MANDATORY: 7-10 questions. Source from Google Autocomplete + PAA boxes for the main keyword.]
    [CRITICAL: ONLY <h3> for questions, <p> for answers. NO <h2>, <h4>, <h5>, NO bullet points inside FAQ.]
    [Each answer: 2-4 sentences, direct and factual. Include main/secondary keyword where natural.]
    [You MAY include 1 relevant Bucketlistt booking link inside a FAQ answer.]

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
