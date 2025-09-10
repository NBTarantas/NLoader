#!/usr/bin/env python3
"""
Debug script for testing file download issues
"""

import requests
import json
import time
import sys
from pathlib import Path

API_BASE = "http://localhost:8000/api"

def test_single_track():
    """Test single track download to debug file issues"""
    print("🎵 Testing single track download...")
    
    # Test with a simple track
    track_url = "https://open.spotify.com/track/4iV5W9uYEdYUVa79Axb7Rh"
    
    try:
        # Start download
        response = requests.post(f"{API_BASE}/download", json={
            "url": track_url,
            "format": "m4a",
            "quality": "320",
            "add_lyrics": False,
            "add_metadata": True
        })
        
        if response.status_code == 200:
            data = response.json()
            download_id = data['download_id']
            print(f"✅ Track download started: {download_id}")
            
            # Monitor progress
            return monitor_download(download_id, "track")
        else:
            print(f"❌ Track download failed: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Track download error: {e}")
        return False

def monitor_download(download_id, content_type):
    """Monitor download progress with detailed logging"""
    print(f"📊 Monitoring {content_type} download progress...")
    
    max_attempts = 30  # 2.5 minutes max
    attempt = 0
    
    while attempt < max_attempts:
        try:
            response = requests.get(f"{API_BASE}/progress/{download_id}")
            if response.status_code == 200:
                data = response.json()
                status = data['status']
                progress = data.get('progress', 0)
                message = data.get('message', '')
                
                print(f"   Progress: {progress}% - {message}")
                
                if status == 'completed':
                    print(f"✅ {content_type.title()} download completed!")
                    
                    # Check if file exists
                    check_downloaded_files(download_id)
                    return True
                elif status == 'error':
                    print(f"❌ {content_type.title()} download failed: {message}")
                    return False
                
                time.sleep(5)  # Wait 5 seconds
                attempt += 1
            else:
                print(f"❌ Progress check failed: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Progress monitoring error: {e}")
            return False
    
    print(f"⏰ {content_type.title()} download timeout after {max_attempts * 5} seconds")
    return False

def check_downloaded_files(download_id):
    """Check what files were actually downloaded"""
    print(f"🔍 Checking downloaded files for {download_id}...")
    
    temp_dir = Path("temp_downloads")
    if not temp_dir.exists():
        print("❌ Temp directory does not exist")
        return
    
    # List all files in temp directory
    all_files = list(temp_dir.glob("*"))
    print(f"📁 All files in temp directory: {len(all_files)}")
    for file in all_files:
        print(f"   - {file.name} ({file.stat().st_size} bytes)")
    
    # Look for files matching our download ID
    matching_files = list(temp_dir.glob(f"{download_id}*"))
    print(f"🎯 Files matching {download_id}: {len(matching_files)}")
    for file in matching_files:
        print(f"   - {file.name} ({file.stat().st_size} bytes)")
        
        # Check file type
        try:
            with open(file, 'rb') as f:
                header = f.read(12)
                print(f"     Header: {header[:8].hex()}")
                
                if header.startswith(b'ftyp'):
                    print(f"     Type: MP4/M4A")
                elif header.startswith(b'OggS'):
                    print(f"     Type: OGG/Opus")
                elif header.startswith(b'ID3'):
                    print(f"     Type: MP3")
                elif header.startswith(b'\xff\xfb'):
                    print(f"     Type: MP3")
                elif header.startswith(b'RIFF'):
                    print(f"     Type: WAV")
                else:
                    print(f"     Type: Unknown")
        except Exception as e:
            print(f"     Error reading file: {e}")

def test_album_download():
    """Test album download with detailed debugging"""
    print("\n💿 Testing album download...")
    
    # Test with a small album
    album_url = "https://open.spotify.com/album/1A2GTWGtFfWp7KSQTwWOyo"
    
    try:
        # Start download
        response = requests.post(f"{API_BASE}/download", json={
            "url": album_url,
            "format": "m4a",
            "quality": "320",
            "add_lyrics": False,
            "add_metadata": True
        })
        
        if response.status_code == 200:
            data = response.json()
            download_id = data['download_id']
            print(f"✅ Album download started: {download_id}")
            
            # Monitor progress
            return monitor_download(download_id, "album")
        else:
            print(f"❌ Album download failed: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Album download error: {e}")
        return False

def main():
    """Run debug tests"""
    print("🐛 Starting Download Debug Tests")
    print("=" * 50)
    
    # Test single track first
    print("1. Testing single track download...")
    track_success = test_single_track()
    
    if track_success:
        print("\n2. Testing album download...")
        album_success = test_album_download()
    else:
        print("Skipping album test due to track failure")
        album_success = False
    
    print("\n" + "=" * 50)
    print("📊 Debug Results:")
    print(f"   Single Track: {'✅ PASS' if track_success else '❌ FAIL'}")
    print(f"   Album: {'✅ PASS' if album_success else '❌ FAIL'}")
    
    if track_success and album_success:
        print("🎉 All tests passed!")
        return 0
    else:
        print("⚠️  Some tests failed - check logs for details")
        return 1

if __name__ == "__main__":
    sys.exit(main())
