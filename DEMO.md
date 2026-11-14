# TaxPilot AI — Hackathon Technical Demo Script (1 Minute)
## Problem Statement Two: "Memory You Can Govern"

> **The Hackathon Challenge:**  
> *"What an agent remembers is data someone has to answer for. Build an agent using MongoDB Atlas and Vector Search to persist and retrieve memory, so that memory changes what it does on the next run, with rules for who can read each memory, how long it lives, and how it gets corrected or forgotten."*

---

## 🎯 The 3 Core Questions Mapped to the 60-Second Demo

```
┌───────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ [0:00 - 0:15] Q1: How do you keep one client's or team's memory from leaking into another's?          │
│               → Server-side Tenant Principal Isolation & Atlas Vector Search User Pre-filtering.       │
├───────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ [0:15 - 0:38] Q2: How does the agent fix or drop a memory that turns out wrong or expired?            │
│               → Atlas Optimistic Concurrency, Atomic Memory Supersession DAG, and Right-to-be-Forgotten.│
├───────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ [0:38 - 1:00] Q3: How do you prove memory changed the agent's behavior and didn't just fill prompt?   │
│               → Mathematical Proof: Memory triggers new bracket (29.65% → 43.41%) & surtax strategy. │
└───────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## ⏱️ Second-by-Second Technical Demo Script

### **0:00 – 0:15 | Question 1: Preventing Multi-Tenant Memory Leaks**
* **On-Screen Action:**
  1. Show dashboard on [http://localhost:8000](http://localhost:8000) with **Alex Mercer** selected in the top persona dropdown. Click the **"Governed Memories"** tab showing Alex's employment and RRSP memories.
  2. Switch the dropdown to **Priya Patel**. Instantly, the memories and profile switch completely to Priya's part-time facts ($18k income, $2.5k limit).
* **Voiceover (Fast & Direct):**
  > *"How do we prevent memory leaks between clients? In TaxPilot, memory isolation is enforced at the server principal layer. Every MongoDB Atlas document and Vector Search query strictly pre-filters by authenticated `user_id`. When we switch from Alex to Priya, her vector embeddings and context are cryptographically walled off—zero cross-tenant leakage."*

---

### **0:15 – 0:38 | Question 2: Fixing, Superseding, and Dropping Expired Memories**
* **On-Screen Action:**
  1. Switch back to **Alex Mercer**. In chat, type and send:  
     `"I received a promotion with a salary increment of 25K effective Dec 1st."`
  2. Show response stream in.
  3. Click **"Governed Memories"** tab: Toggle **"Show Superseded"** checkbox.
     - Show the old salary memory tagged with amber badge `superseded`.
     - Show the new memory tagged with green badge `active` (`v2`).
  4. Point to the **"Erase"** button on a memory:
     - Click **"Erase"**: it instantly deletes vector embeddings and tags status `deleted`, writing an immutable record to the **Audit Trail**.
* **Voiceover:**
  > *"How do we fix or drop wrong memories? We don't blindly append or delete. In MongoDB Atlas, our LangGraph agent executes an atomic supersession DAG with optimistic concurrency. The old salary memory is permanently linked and marked `superseded`, while the new $130,000 fact becomes `active` with fresh vector embeddings. Users have sovereign control: one click on 'Erase' purges the vector and content while preserving an audit log."*

---

### **0:38 – 0:52 | Question 3: Proving Memory Changed Agent Behavior**
* **On-Screen Action:**
  1. Click **"Profile & Diff"** tab.
  2. Scroll to the **"Circumstance Change & Reassessment Comparison"** card:
     - Highlight: **Baseline ($85,000 CAD)**: Marginal rate `29.65%`, $5,000 RRSP savings = **$1,482.50 CAD**.
     - Highlight: **Active Memory ($130,000 CAD)**: Marginal rate `43.41%`, $5,000 RRSP savings = **$2,170.48 CAD** (+$687.98 difference!).
  3. Click **"Recommendations"** tab:
     - Show that the agent automatically branched to generate the **"Ontario Surtax Mitigation"** strategy because memory told it the user crossed the provincial $100k threshold.
* **Voiceover:**
  > *"How do we prove memory changed behavior instead of just filling prompt context? Mathematical proof. On the subsequent run, retrieving the active $130,000 memory didn't just re-populate text—it deterministically shifted Alex from the 29.65% to the 43.41% marginal bracket, altering tax savings from $1,482 to $2,170, and automatically generating an Ontario Surtax mitigation strategy."*

---

### **0:52 – 1:00 | Conclusion & Impact**
* **On-Screen Action:**
  - Click **"Audit Trail"** tab showing the chronological log of `supersede`, `create`, and `erase` events.
  - Flash GitHub repository page: `github.com/jotchatwal/tax_agents`.
* **Voiceover:**
  > *"MongoDB Atlas Vector Search. LangGraph deterministic reasoning. Zero LLM hallucinations. TaxPilot AI delivers memory you can truly govern. Explore our code on GitHub!"*

---

## 📋 Exact Screen Recording Checklist & Shortcuts

| Step | Action | Keyboard / Mouse | Target Result |
| :---: | :--- | :--- | :--- |
| **1** | Start on Alex Mercer | Open Chrome on `http://127.0.0.1:8000` | Profile & Diff visible |
| **2** | Switch to Priya Patel | Click dropdown at top right | Dashboard clears Alex & loads Priya's $18k profile |
| **3** | Switch back to Alex | Click dropdown $\to$ Alex Mercer | Alex's profile re-loads |
| **4** | Send Promo Message | Paste: `"I received a promotion with a salary increment of 25K effective Dec 1st."` | Bot acknowledges $130k and supersedes old memory |
| **5** | Click "Governed Memories" | Click 2nd tab $\to$ Check "Show Superseded" | Shows green `active` and amber `superseded` |
| **6** | Click "Profile & Diff" | Click 1st tab | Shows Circumstance Diff ($1,482 $\to$ $2,170) |
| **7** | Click "Recommendations" | Click 3rd tab | Shows Ontario Surtax Mitigation card |
| **8** | Click "Audit Trail" | Click 5th tab | Shows immutable audit logs |
