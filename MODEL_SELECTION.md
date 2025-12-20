# Model Selection Guide

## 🎯 How Model Selection Works

When configuring agents (Bias Agent, Strategy Agent), you can select different AI models. The system intelligently routes requests based on your selection:

### Model Options:

| Model Selection | Behavior | Cost | Quality | Requirements |
|----------------|----------|------|---------|--------------|
| **lm-studio** | Uses your local LM Studio instance | ✅ **FREE** | Good | LM Studio running with function-calling model |
| **gpt-3.5-turbo** | Uses OpenAI API | 💰 Paid | Very Good | OpenAI API credits |
| **gpt-4** | Uses OpenAI API | 💰💰 Paid | Excellent | OpenAI API credits |
| **gpt-4o** | Uses OpenAI API | 💰💰 Paid | Excellent | OpenAI API credits |

---

## 📋 Behavior Details

### Option 1: "lm-studio" (Recommended for Development)

**What happens:**
- Uses whatever model you have loaded in LM Studio
- Connects to `http://host.docker.internal:1234/v1`
- **Free** - no API costs
- Good for testing and development

**Requirements:**
- LM Studio running on port 1234
- Function-calling capable model loaded (e.g., Hermes-2-Pro-Mistral-7B)
- Model properly configured in LM Studio

**Current Setup:**
- ✅ Hermes-2-Pro-Mistral-7B is loaded
- ✅ Function calling works
- ✅ Tools execute properly

---

### Option 2: "gpt-3.5-turbo" / "gpt-4" / "gpt-4o" (Production)

**What happens:**
- Connects directly to `https://api.openai.com/v1`
- Uses your OpenAI API key from `.env`
- **Costs money** based on token usage
- Best quality and reliability

**Requirements:**
- Valid `OPENAI_API_KEY` in `.env`
- OpenAI account with sufficient credits
- Internet connection

**When to use:**
- Production pipelines
- When you need highest quality analysis
- When local model quality isn't sufficient

---

## 🔧 Configuration

### .env File Setup

```bash
# For LM Studio (local)
OPENAI_API_KEY=lm-studio  # Can be any value
OPENAI_BASE_URL=http://host.docker.internal:1234/v1

# For OpenAI API (cloud)
OPENAI_API_KEY=sk-proj-...your-actual-key...
OPENAI_BASE_URL=https://api.openai.com/v1
```

**Current Setup:** Using LM Studio (local)

---

## 🎮 How to Switch Models

### In the UI:

1. Open agent configuration (Bias Agent or Strategy Agent)
2. Select "AI Model" dropdown
3. Choose:
   - **"lm-studio"** → Free, local, good quality
   - **"gpt-4"** → Paid, cloud, best quality

### What Happens Behind the Scenes:

```python
if model == "lm-studio":
    # Route to LM Studio
    url = "http://host.docker.internal:1234/v1"
    # Uses whatever model you have loaded (Hermes-2-Pro-Mistral-7B)
    
elif model in ["gpt-3.5-turbo", "gpt-4", "gpt-4o"]:
    # Route to OpenAI API
    url = "https://api.openai.com/v1"
    # Uses the specific OpenAI model
```

---

## 🚨 Important Notes

### About Local Models:

1. **Model name doesn't matter** - LM Studio ignores the model name in requests and always uses the model you have loaded in the UI
2. **Function calling required** - Your model MUST support function calling for tools to work
3. **Recommended models**:
   - ✅ Hermes-2-Pro-Mistral-7B (currently loaded)
   - ✅ NousResearch/Hermes-3-Llama-3.1-8B
   - ✅ meetkai/functionary-small-v2.5

### About OpenAI Models:

1. **Requires credits** - Make sure your OpenAI account has available credits
2. **Usage costs** - Charges per token (input + output)
3. **Best quality** - Native function calling, best reasoning

---

## 📊 Comparison

| Feature | lm-studio | gpt-4 |
|---------|-----------|-------|
| **Cost** | Free | ~$0.01-0.10 per agent run |
| **Speed** | Fast (local) | Slower (API call) |
| **Quality** | Good | Excellent |
| **Function Calling** | ✅ (with right model) | ✅ Native |
| **Privacy** | ✅ All local | ❌ Sent to OpenAI |
| **Offline** | ✅ Works offline | ❌ Requires internet |

---

## 🎯 Recommendations

### For Development/Testing:
- Use **"lm-studio"**
- Free and fast
- Good enough quality for testing

### For Production:
- Use **"gpt-4"** or **"gpt-4o"**
- Best quality and reliability
- Worth the cost for real trading decisions

### For Budget-Conscious:
- Use **"lm-studio"** with Hermes-2-Pro
- Quality is good for most use cases
- Zero ongoing costs

---

## 🔧 Troubleshooting

### Tools Not Executing (lm-studio):
- Make sure LM Studio is running on port 1234
- Verify you have a function-calling model loaded (Hermes-2-Pro, Functionary, etc.)
- Check `docker-compose logs backend` for connection errors

### OpenAI Quota Exceeded (gpt-3.5/gpt-4):
- Add credits at https://platform.openai.com/account/billing
- Or switch to "lm-studio" in agent configuration

### Model Quality Issues:
- Try upgrading to gpt-4 (better than gpt-3.5-turbo)
- Or try a different local model in LM Studio
- Adjust agent instructions to be more specific

---

## ✅ Current Status

- ✅ LM Studio configured and working
- ✅ Hermes-2-Pro-Mistral-7B loaded
- ✅ Function calling enabled
- ✅ Tools executing properly
- ✅ Model selection UI available
- ✅ Smart routing implemented

You can now select models per agent based on your needs!

