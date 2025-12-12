import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface FileUploadResponse {
  file_url: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  extracted_text?: string;
}

@Injectable({
  providedIn: 'root'
})
export class FileUploadService {
  private readonly apiUrl = `${environment.apiUrl}/api/v1/files`;

  constructor(private http: HttpClient) {}

  /**
   * Upload a file (PDF, image, etc.)
   */
  uploadFile(file: File, extractText: boolean = true): Observable<FileUploadResponse> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('extract_text', extractText.toString());

    return this.http.post<FileUploadResponse>(
      `${this.apiUrl}/upload`,
      formData
    );
  }

  /**
   * Delete an uploaded file
   */
  deleteFile(fileUrl: string): Observable<any> {
    return this.http.delete(`${this.apiUrl}/delete`, {
      params: { file_url: fileUrl }
    });
  }
}

