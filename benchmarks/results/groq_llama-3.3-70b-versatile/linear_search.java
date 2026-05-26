import java.util.Scanner;

public class LinearSearch {
    public static int linearSearch(int[] arr, int n, int target) {
        int i;
        for (i = 0; i < n; i++) {
            if (arr[i] == target) {
                return i;  // Found at index i
            }
        }
        return -1;  // Not found
    }

    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int n, target, i, result;
        int[] arr = new int[100];
        n = scanner.nextInt();
        if (n > 100) n = 100;
        for (i = 0; i < n; i++) {
            arr[i] = scanner.nextInt();
        }
        target = scanner.nextInt();
        
        System.out.print("Array: ");
        for (i = 0; i < n; i++) {
            System.out.print(arr[i] + " ");
        }
        System.out.println();
        
        result = linearSearch(arr, n, target);
        
        if (result != -1) {
            System.out.println("Element " + target + " found at index " + result);
        } else {
            System.out.println("Element " + target + " not found");
        }
        
        scanner.close();
    }
}