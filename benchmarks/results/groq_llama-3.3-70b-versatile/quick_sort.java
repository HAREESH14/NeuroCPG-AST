import java.util.Scanner;

public class QuickSort {
    public static void swap(int[] a, int i, int j) {
        int t = a[i]; 
        a[i] = a[j]; 
        a[j] = t;
    }

    public static int partition(int[] a, int low, int high) {
        int pivot = a[high];
        int i = low - 1;
        for (int j = low; j <= high - 1; j++) {
            if (a[j] < pivot) { 
                i++; 
                swap(a, i, j); 
            }
        }
        swap(a, i+1, high);
        return i+1;
    }

    public static void quick_sort(int[] a, int low, int high) {
        if (low < high) {
            int pi = partition(a, low, high);
            quick_sort(a, low, pi - 1);
            quick_sort(a, pi + 1, high);
        }
    }

    public static void print_array(int[] a, int n) { 
        for (int i=0;i<n;i++) System.out.print(a[i] + " "); 
        System.out.println(); 
    }

    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int n = scanner.nextInt();
        int[] arr = new int[100];
        if (n > 100) n = 100;
        for (int i = 0; i < n; i++) arr[i] = scanner.nextInt();
        System.out.print("Original: "); 
        print_array(arr, n);
        quick_sort(arr, 0, n-1);
        System.out.print("Sorted:   "); 
        print_array(arr, n);
    }
}