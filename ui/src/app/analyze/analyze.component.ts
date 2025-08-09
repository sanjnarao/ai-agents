import { Component, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient, HttpClientModule, HttpEventType } from '@angular/common/http';
import { FormsModule } from '@angular/forms';

@Component({
  standalone: true,
  selector: 'app-analyze',
  imports: [CommonModule, HttpClientModule, FormsModule],
  templateUrl: './analyze.component.html',
  styleUrls: ['./analyze.component.css']
})
export class AnalyzeComponent {
  apiBase = 'http://127.0.0.1:8000';
  zipFile: File | null = null;
  docFiles: File[] = [];
  isUploading = signal(false);
  resultMarkdown = signal<string>('');
  error = signal<string>('');

  constructor(private http: HttpClient) {}

  onZipChange(ev: Event) {
    const input = ev.target as HTMLInputElement;
    this.zipFile = input.files?.[0] ?? null;
  }

  onDocsChange(ev: Event) {
    const input = ev.target as HTMLInputElement;
    this.docFiles = input.files ? Array.from(input.files) : [];
  }

  submit() {
    this.error.set('');
    this.resultMarkdown.set('');
    if (!this.zipFile) {
      this.error.set('Please select a ZIP that contains your .sln and projects.');
      return;
    }
    const fd = new FormData();
    fd.append('solution_zip', this.zipFile);
    for (const f of this.docFiles) fd.append('extra_docs', f);

    this.isUploading.set(true);
    this.http.post<{ markdown: string }>(`${this.apiBase}/api/analyze`, fd)
      .subscribe({
        next: res => {
          this.resultMarkdown.set(res.markdown || '');
          this.isUploading.set(false);
        },
        error: (err) => {
          this.error.set(err?.error?.detail || 'Request failed');
          this.isUploading.set(false);
        }
      });
  }
}
