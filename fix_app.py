import io
with io.open('frontend/src/App.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Regex injection
content = content.replace(
    "const parts = match.text.split(new RegExp(`(${searchQuery.trim()})`, 'gi'));",
    "const escaped = searchQuery.trim().replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&');\n                                  const parts = match.text.split(new RegExp(`(${escaped})`, 'gi'));"
)

# 2. syncProgress div 0
content = content.replace(
    "{syncProgress.current}/{syncProgress.total} ({Math.round((syncProgress.current / syncProgress.total) * 100)}%)",
    "{syncProgress.current}/{syncProgress.total} ({syncProgress.total > 0 ? Math.round((syncProgress.current / syncProgress.total) * 100) : 0}%)"
)
content = content.replace(
    "style={{ width: `${(syncProgress.current / syncProgress.total) * 100}%` }}",
    "style={{ width: `${syncProgress.total > 0 ? (syncProgress.current / syncProgress.total) * 100 : 0}%` }}"
)

# 3. transcriptionStatus div 0
content = content.replace(
    "{transcriptionStatus.current_index}/{transcriptionStatus.total_to_process} ({Math.round((transcriptionStatus.current_index / transcriptionStatus.total_to_process) * 100)}%)",
    "{transcriptionStatus.current_index}/{transcriptionStatus.total_to_process} ({transcriptionStatus.total_to_process > 0 ? Math.round((transcriptionStatus.current_index / transcriptionStatus.total_to_process) * 100) : 0}%)"
)
content = content.replace(
    "style={{ width: `${(transcriptionStatus.current_index / transcriptionStatus.total_to_process) * 100}%` }}",
    "style={{ width: `${transcriptionStatus.total_to_process > 0 ? (transcriptionStatus.current_index / transcriptionStatus.total_to_process) * 100 : 0}%` }}"
)

# 4. formatETA < 1 min (I will skip this one to avoid thai text, or just replace the math)
# I can just use line replacement for ETA
content = content.replace(
    "    if (h > 0)",
    "    if (m === 0) return \"\\u0E04\\u0E32\\u0E14\\u0E27\\u0E48\\u0E32\\u0E08\\u0E30\\u0E40\\u0E2A\\u0E23\\u0E47\\u0E08\\u0E43\\u0E19\\u0E2D\\u0E35\\u0E01\\u0E44\\u0E21\\u0E48\\u0E16\\u0E36\\u0E07 1 \\u0E19\\u0E32\\u0E17\\u0E35\";\n    if (h > 0)"
)

# 5. Dashboard Poll Stale closure
content = content.replace(
    "  }, [activeTab, videos]);",
    "  }, [activeTab]);"
)

# 6. double click summarize guard
content = content.replace(
    "    setVideoSummaries(prev => ({\n      ...prev,\n      [videoId]: { loading: true }\n    }));",
    "    if (videoSummaries[videoId]?.loading) return;\n    setVideoSummaries(prev => ({\n      ...prev,\n      [videoId]: { loading: true }\n    }));"
)

# 7. handleCopyLink try catch (using unicode escapes for thai text)
content = content.replace(
    "  const handleCopyLink = (videoId: string, seconds: number) => {\n    const url = `https://youtu.be/${videoId}?t=${Math.floor(seconds)}`;\n    navigator.clipboard.writeText(url);\n    addToast(\"\\u0E04\\u0E31\\u0E14\\u0E25\\u0E2D\\u0E01\\u0E25\\u0E34\\u0E07\\u0E01\\u0E4C\\u0E44\\u0E1B\\u0E22\\u0E31\\u0E07\\u0E04\\u0E25\\u0E34\\u0E1B\\u0E1A\\u0E2D\\u0E23\\u0E4C\\u0E14\\u0E41\\u0E25\\u0E49\\u0E27!\", \"success\");\n  };",
    "  const handleCopyLink = async (videoId: string, seconds: number) => {\n    const url = `https://youtu.be/${videoId}?t=${Math.floor(seconds)}`;\n    try {\n      await navigator.clipboard.writeText(url);\n      addToast(\"\\u0E04\\u0E31\\u0E14\\u0E25\\u0E2D\\u0E01\\u0E25\\u0E34\\u0E07\\u0E01\\u0E4C\\u0E44\\u0E1B\\u0E22\\u0E31\\u0E07\\u0E04\\u0E25\\u0E34\\u0E1B\\u0E1A\\u0E2D\\u0E23\\u0E4C\\u0E14\\u0E41\\u0E25\\u0E49\\u0E27!\", \"success\");\n    } catch {\n      addToast(\"\\u0E44\\u0E21\\u0E48\\u0E2A\\u0E32\\u0E21\\u0E32\\u0E23\\u0E16\\u0E04\\u0E31\\u0E14\\u0E25\\u0E2D\\u0E01\\u0E25\\u0E34\\u0E07\\u0E01\\u0E4C\\u0E44\\u0E14\\u0E49\", \"error\");\n    }\n  };"
)

# 8. searchHistory map key
content = content.replace(
    "                  {searchHistory.map((h, i) => (\n                    <span\n                      key={i}",
    "                  {searchHistory.map((h, i) => (\n                    <span\n                      key={h}"
)

# 9. modal scroll lock
content = content.replace(
    "  const fetchVideos = async (targetChannel: string) => {",
    "  useEffect(() => {\n    if (activeTranscriptVideoId) {\n      document.body.style.overflow = \"hidden\";\n      const handleEscape = (e: KeyboardEvent) => {\n        if (e.key === \"Escape\") setActiveTranscriptVideoId(null);\n      };\n      document.addEventListener(\"keydown\", handleEscape);\n      return () => {\n        document.body.style.overflow = \"\";\n        document.removeEventListener(\"keydown\", handleEscape);\n      };\n    }\n  }, [activeTranscriptVideoId]);\n\n  const fetchVideos = async (targetChannel: string) => {"
)

with io.open('frontend/src/App.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
