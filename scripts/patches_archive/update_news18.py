import yaml
import os

base_dir = "/home/owl/text_analytics/project/veritas_lens_alt"
conf_path_1 = os.path.join(base_dir, "config", "sources.yaml")
conf_path_2 = os.path.join(base_dir, "ingestion", "config", "sources.yaml")

def update_sources(conf_path):
    with open(conf_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    for source in data.get("sources", []):
        if source["slug"] == "news18_tamil_nadu":
            source["rss"] = [
                "https://tamil.news18.com/commonfeeds/v1/tam/rss/national.xml",
                "https://tamil.news18.com/commonfeeds/v1/tam/rss/international.xml",
                "https://tamil.news18.com/commonfeeds/v1/tam/rss/tamil-nadu.xml"
            ]
        elif source["slug"] == "news18_india":
            source["rss"] = [
                "https://www.news18.com/commonfeeds/v1/eng/rss/india.xml",
                "https://www.news18.com/commonfeeds/v1/eng/rss/world.xml"
            ]
            
    with open(conf_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)

update_sources(conf_path_1)
update_sources(conf_path_2)
print("Updated YAML configs successfully.")
